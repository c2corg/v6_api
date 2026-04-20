import logging

import transaction
from kombu.pools import producers

log = logging.getLogger(__name__)


def notify_es_syncer(queue_config):
    """When the current transaction is committed successfully, notify the
    syncer script that a document has changed by pushing a friendly message
    into the Redis queue.
    """

    def push_notification():
        def on_revive(channel):
            """Try to re-create the Redis queue on connection errors."""
            try:
                # try to unbind the queue, ignore errors
                channel.queue_unbind(
                    queue_config.queue.name, exchange=queue_config.exchange.name
                )
            except Exception:
                pass

            # the re-create the queue
            channel.queue_bind(
                queue_config.queue.name, exchange=queue_config.exchange.name
            )

        with producers[queue_config.connection].acquire(
            block=True, timeout=3
        ) as producer:
            log.info('Notifying ElasticSearch syncer')
            producer.publish(
                'please sync',
                exchange=queue_config.exchange,
                declare=[queue_config.exchange, queue_config.queue],
                retry=True,
                retry_policy={'max_retries': 3, 'on_revive': on_revive},
            )

    run_on_successful_transaction(push_notification)


def run_on_successful_transaction(operation):
    """Run the given operation when the current transaction is committed
    successfully.
    """

    def run_when_successful(success, *args, **kws):
        if success:
            try:
                operation()
            except Exception:
                log.error('Scheduled operation failed', exc_info=True)
        else:
            log.warning(
                'Scheduled operation is not run because transaction was not successful'
            )

    current_transaction = transaction.get()
    current_transaction.addAfterCommitHook(run_when_successful)


def notify_es_syncer_immediate(queue_config):
    """Push an ES sync notification *immediately* — without relying on
    ``transaction`` commit hooks.

    Used by FastAPI code paths where the session is committed by the
    ``get_db`` dependency (plain ``db.commit()``) rather than via
    ``zope.sqlalchemy`` / ``pyramid_tm``.
    """

    def on_revive(channel):
        try:
            channel.queue_unbind(
                queue_config.queue.name, exchange=queue_config.exchange.name
            )
        except Exception:
            pass
        channel.queue_bind(queue_config.queue.name, exchange=queue_config.exchange.name)

    try:
        with producers[queue_config.connection].acquire(
            block=True, timeout=3
        ) as producer:
            log.info('Notifying ElasticSearch syncer (immediate)')
            producer.publish(
                'please sync',
                exchange=queue_config.exchange,
                declare=[queue_config.exchange, queue_config.queue],
                retry=True,
                retry_policy={'max_retries': 3, 'on_revive': on_revive},
            )
    except Exception:
        log.error('Immediate ES sync notification failed', exc_info=True)
