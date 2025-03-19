import transaction
from c2corg_api.queues.queues_service import publish
import logging

log = logging.getLogger(__name__)


def notify_es_syncer(queue_config):
    """When the current transaction is committed successfully, notify the
    syncer script that a document has changed by pushing a friendly message
    into the Redis queue.
    """
    log.info('Notifying ElasticSearch syncer')
    run_on_successful_transaction(publish(queue_config, 'please sync'))


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
            log.warning('Scheduled operation is not run because transaction '
                        'was not successful')

    current_transaction = transaction.get()
    current_transaction.addAfterCommitHook(run_when_successful)
