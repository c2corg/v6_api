import atexit
import logging

from apscheduler.events import EVENT_JOB_ERROR
from apscheduler.schedulers.background import BackgroundScheduler

from c2corg_api.jobs.process_removals import process_removals, removals_auto
from c2corg_api.jobs.purge_deleted_documents import purge_deleted_documents
from c2corg_api.jobs.purge_expired_tokens import purge_token
from c2corg_api.jobs.purge_non_activated_accounts import purge_account

log = logging.getLogger(__name__)


def exception_listener(event):
    log.exception('The job crashed')


def configure_scheduler_from_config(settings):
    scheduler = BackgroundScheduler()
    scheduler.start()

    # run `purge_account` job at 0:00
    scheduler.add_job(
        purge_account,
        id='purge_account',
        name='Purge accounts which where not activated',
        trigger='cron',
        hour=0,
        minute=0,
    )

    # run `purge_token` job every hour, at :30: it also closes the forum
    # session of the users whose token expired (a token may last a day)
    scheduler.add_job(
        purge_token,
        id='purge_token',
        name='Purge expired tokens',
        trigger='cron',
        minute=30,
        kwargs={'settings': settings},
    )

    # run `purge_deleted_documents` job at 1:00
    scheduler.add_job(
        purge_deleted_documents,
        id='purge_deleted_documents',
        name='Purge the deleted documents kept longer than the retention',
        trigger='cron',
        hour=1,
        minute=0,
    )

    # run `process_removals` every hour, at :15, once switched on: the first
    # removals are run by hand (scripts/users/process_removals.py)
    if removals_auto(settings):
        scheduler.add_job(
            process_removals,
            id='process_removals',
            name='Remove the accounts of the validated removal requests',
            trigger='cron',
            minute=15,
            kwargs={'settings': settings},
        )

    scheduler.add_listener(exception_listener, EVENT_JOB_ERROR)

    atexit.register(lambda: scheduler.shutdown())
