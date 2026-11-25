import logging
from datetime import UTC, datetime

from c2corg_api.models import DBSession
from c2corg_api.scripts.users.process_removals import find_ready_requests, process_all
from c2corg_api.search import get_queue_config
from c2corg_api.security.discourse_client import get_discourse_client

log = logging.getLogger(__name__)


def removals_auto(settings):
    """Tell whether the scheduler removes the accounts (`users.removals.auto`)."""
    value = str(settings.get('users.removals.auto', 'false')).strip().lower()
    return value in ('true', '1', 'yes', 'on')


def process_removals(settings):
    """Remove the accounts of the validated removal requests that are ready."""
    # The same steps as scripts/users/process_removals.py --execute. A failed
    # request is logged and stays open: the next run tries it again.
    if not get_discourse_client(settings).enabled:
        log.warning('The forum is disabled: no account removed')
        return
    # DBSession is scoped by thread: this job's session is closed at the end
    try:
        removals = find_ready_requests(datetime.now(UTC))
        if removals:
            log.info('Processing %d account removal requests', len(removals))
            failed = process_all(removals, settings, get_queue_config(settings))
            if failed:
                log.error('%d account removal requests failed', failed)
    finally:
        DBSession.remove()
