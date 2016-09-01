import atexit
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.events import EVENT_JOB_ERROR

from c2corg_api.jobs.purge_non_activated_accounts import purge_account
from c2corg_api.jobs.purge_expired_tokens import purge_token

import logging
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
        minute=0
    )

    # run `purge_token` job at 0:30
    scheduler.add_job(
        purge_token,
        id='purge_token',
        name='Purge expired tokens',
        trigger='cron',
        hour=0,
        minute=30
    )

    scheduler.add_listener(exception_listener, EVENT_JOB_ERROR)

    atexit.register(lambda: scheduler.shutdown())
