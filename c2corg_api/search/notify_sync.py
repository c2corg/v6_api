import logging

from sqlalchemy import event
from sqlalchemy.orm import Session

from c2corg_api.models import DBSession
from c2corg_api.queues.queues_service import publish

log = logging.getLogger(__name__)


def notify_es_syncer(queue_config):
    """Notify the ES syncer of a changed document after commit.

    When the current transaction is committed successfully, notify the
    syncer script that a document has changed by pushing a friendly message
    into the Redis queue.
    """

    def push_notification():
        log.info('Notifying ElasticSearch syncer')
        publish(queue_config, 'please sync')

    run_on_successful_transaction(push_notification)


# the operations of a session to run once its transaction is committed
_AFTER_COMMIT = 'c2corg_after_commit'


def run_on_successful_transaction(operation):
    """Run the given operation once the transaction is committed."""
    # the transaction of the session of the current thread (DBSession),
    # started if needed so that its end decides: run on commit, dropped on
    # rollback
    session = DBSession()
    session.connection()
    session.info.setdefault(_AFTER_COMMIT, []).append(operation)


@event.listens_for(Session, 'after_commit')
def _run_after_commit(session):
    for operation in session.info.pop(_AFTER_COMMIT, []):
        try:
            operation()
        except Exception:
            log.error('Scheduled operation failed', exc_info=True)


@event.listens_for(Session, 'after_soft_rollback')
def _drop_after_rollback(session, previous_transaction):
    if session.info.pop(_AFTER_COMMIT, None):
        log.warning(
            'Scheduled operation is not run because transaction was not successful'
        )
