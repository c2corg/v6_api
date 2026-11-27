import atexit
import logging

from apscheduler.events import EVENT_JOB_ERROR
from apscheduler.schedulers.background import BackgroundScheduler

from c2corg_api.harvest.runner import enabled_harvesters, harvest_tick

# the module, not its function of the same name: importing the function here
# would hide the submodule (`c2corg_api.jobs.harvest_partner_outings`)
from c2corg_api.jobs import harvest_partner_outings as partner_outings
from c2corg_api.jobs.harvest import compact_avalanche_bulletins, prune_harvest
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

    # harvest the sources (avalanche bulletins, partner outings...) once
    # switched on (harvest.enabled, harvest.<name>.enabled): each source says
    # when it is due; a tick still running makes the next wait
    if enabled_harvesters(settings):
        scheduler.add_job(
            harvest_tick,
            id='harvest_tick',
            name='Harvest the due sources',
            trigger='interval',
            minutes=1,
            max_instances=1,
            coalesce=True,
            kwargs={'settings': settings},
        )
        # run `prune_harvest` at 2:00
        scheduler.add_job(
            prune_harvest,
            id='prune_harvest',
            name='Prune the old harvest payloads and superseded bulletins',
            trigger='cron',
            hour=2,
            minute=0,
        )
        # run `compact_avalanche_bulletins` the 1st of each month at 3:00
        scheduler.add_job(
            compact_avalanche_bulletins,
            id='compact_avalanche_bulletins',
            name='Remove the customData of the bulletins older than 18 months',
            trigger='cron',
            day=1,
            hour=3,
            minute=0,
        )

    # run `purge_partner_outings_job` at 1:40, whether the harvest is on or not:
    # it expires the lookup cache; the outings and their tracks are kept
    # forever unless a retention is set (`partners.retention_days`)
    scheduler.add_job(
        partner_outings.purge_partner_outings_job,
        id='purge_partner_outings',
        name='Purge the old partner outings and lookups',
        trigger='cron',
        hour=1,
        minute=40,
        kwargs={'settings': settings},
    )

    # mark the partner sources switched off as disabled, once at the start:
    # the switches (harvest.partners[.<name>].enabled) change with a restart
    scheduler.add_job(
        partner_outings.mark_unconfigured_sources,
        id='mark_unconfigured_partner_sources',
        name='Mark the partner sources switched off as disabled',
        trigger='date',
        kwargs={'settings': settings},
    )

    scheduler.add_listener(exception_listener, EVENT_JOB_ERROR)

    atexit.register(lambda: scheduler.shutdown())
