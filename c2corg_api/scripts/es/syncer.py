import logging
import sys
import os
from c2corg_api.queues.queues_service import get_queue_config
from c2corg_api.scripts.es.sync import sync_es
from c2corg_api.search import configure_es_from_config
from pyramid.scripts.common import parse_vars
from pyramid.paster import get_appsettings, setup_logging
from sqlalchemy import engine_from_config

from kombu.mixins import ConsumerMixin
from sqlalchemy.orm import sessionmaker

log = logging.getLogger('c2corg_api_syncer')


class SyncWorker(ConsumerMixin):
    """Worker that listens to messages in the Redis queue and then synchronizes
    changes that have been made in the Postgres database with ElasticSearch.

    Based on this example:
    http://docs.celeryproject.org/projects/kombu/en/latest/userguide/examples.html
    """

    def __init__(
            self, connection, queue, batch_size, session=None,
            session_factory=None):
        self.connection = connection
        self.queue = queue
        self.batch_size = batch_size
        self.session = session
        self.session_factory = session_factory
        self.connect_max_retries = 3

    def get_consumers(self, consumer_factory, channel):
        return [consumer_factory(
            queues=[self.queue], callbacks=[self.process_task])]

    def process_task(self, body, message):
        log.info('Sync requested')
        # the sync request is confirmed even though it might fail. in this case
        # a new request will trigger a new sync, or manual interaction is
        # required.
        message.ack()
        try:
            self.sync()
        except Exception:
            log.error('Sync failed', exc_info=True)
        log.info('Waiting on messages')

    def sync(self):
        session = self.session if self.session else self.session_factory()
        try:
            sync_es(session, self.batch_size)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


def usage(argv):
    cmd = os.path.basename(argv[0])
    print('usage: %s <config_uri> [var=value]\n'
          '(example: "%s development.ini")' % (cmd, cmd))
    sys.exit(1)


def main(argv=sys.argv):
    if len(argv) < 2:
        usage(argv)
    config_uri = argv[1]
    options = parse_vars(argv[2:])
    setup_logging(config_uri)

    # configure connections for Postgres, ElasticSearch and Redis
    settings = get_appsettings(config_uri, options=options)
    engine = engine_from_config(settings, 'sqlalchemy.')
    Session = sessionmaker()  # noqa
    Session.configure(bind=engine)
    configure_es_from_config(settings)
    queue_config = get_queue_config(settings, settings['redis.queue_es_sync'])
    batch_size = int(settings.get('elasticsearch.batch_size.syncer', 1000))

    with queue_config.connection:
        try:
            worker = SyncWorker(
                queue_config.connection, queue_config.queue, batch_size,
                session_factory=Session)
            log.info('Syncer started, running initial sync')
            worker.sync()
            log.info('Waiting on messages')
            worker.run()
        except KeyboardInterrupt:
            log.info('Syncer stopped')


if __name__ == "__main__":
    main()
