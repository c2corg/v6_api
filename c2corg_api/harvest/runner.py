"""Run the harvesters: fetch the due sources, store and record the results."""

import gzip
import logging
import random
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from c2corg_api.harvest.harvester import NotModified, State
from c2corg_api.harvest.policy import next_run
from c2corg_api.models import DBSession
from c2corg_api.models.harvest import HarvestPayload, HarvestSource

log = logging.getLogger(__name__)

WORKERS = 4
# be gentle with each service
PER_HOST = 2
# the sources claimed by a tick: those left wait for the next one
CLAIMS = 60
# a claimed source whose run died (a crash, a restart) is fetched again after
LEASE = timedelta(minutes=10)
PAYLOAD_RETENTION = timedelta(days=30)
# what is kept of an error message
ERROR_LENGTH = 1000

_hosts_lock = threading.Lock()
_hosts = defaultdict(lambda: threading.BoundedSemaphore(PER_HOST))


def harvesters():
    """Return the harvesters run by the scheduler."""
    from c2corg_api.avalanche_bulletins.harvesters import (
        CaamlHarvester,
        MeteoFranceHarvester,
    )

    return [MeteoFranceHarvester(), CaamlHarvester()]


def harvest_enabled(settings):
    """Tell whether the scheduler harvests (`harvest.enabled`)."""
    value = str(settings.get('harvest.enabled', 'false')).strip().lower()
    return value in ('true', '1', 'yes', 'on')


def harvest_tick(all_harvesters=None, workers=WORKERS):
    """Fetch the sources whose time has come (the job of every minute)."""
    by_name = {h.name: h for h in (all_harvesters or harvesters())}
    # A plain session on the engine configured on DBSession, as the other
    # jobs; each source then stores in its own session, in its thread.
    with Session(DBSession.get_bind()) as session:
        sync_sources(session, by_name.values())
        claimed = claim(session, by_name)
    tasks = [(by_name[name], id, state) for name, id, state in claimed]
    if workers <= 1:
        for task in tasks:
            run_source(*task)
        return
    with ThreadPoolExecutor(workers, thread_name_prefix='harvest') as executor:
        # run_source records its errors: nothing to collect
        list(executor.map(lambda task: run_source(*task), tasks))


def sync_sources(session, all_harvesters):
    """Add the new sources of the harvesters (due now), remove the gone ones."""
    for harvester in all_harvesters:
        wanted = {harvester.source_id(source) for source in harvester.sources()}
        known = set(
            session.scalars(
                select(HarvestSource.id).where(
                    HarvestSource.harvester == harvester.name
                )
            )
        )
        if wanted - known:
            session.execute(
                insert(HarvestSource)
                .values(
                    [
                        {'id': id, 'harvester': harvester.name, 'next_run_at': _now()}
                        for id in sorted(wanted - known)
                    ]
                )
                .on_conflict_do_nothing()
            )
        if known - wanted:
            session.execute(
                delete(HarvestSource).where(HarvestSource.id.in_(known - wanted))
            )
    session.commit()


def claim(session, by_name, limit=CLAIMS):
    """Claim the due sources: (harvester name, source id, state), committed."""
    # SKIP LOCKED: the sources claimed meanwhile by another scheduler are left
    # to it; LEASE: the run of each source moves next_run_at again
    now = _now()
    sources = session.scalars(
        select(HarvestSource)
        .where(
            HarvestSource.harvester.in_(list(by_name)),
            HarvestSource.next_run_at <= now,
        )
        .order_by(HarvestSource.next_run_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()
    claimed = []
    for source in sources:
        source.next_run_at = now + LEASE
        source.last_attempt = now
        claimed.append((source.harvester, source.id, _state_of(source)))
    session.commit()
    return claimed


def run_source(harvester, source_id, state):
    """Fetch a source, store what is new, and record when to come back."""
    source = source_id.removeprefix(f'{harvester.name}:')
    try:
        with _host_slot(harvester.host(source)):
            payload = harvester.fetch(source, state)
    except NotModified:
        payload = None
    except Exception as e:
        _record_error(harvester, source_id, e)
        return
    try:
        with Session(DBSession.get_bind()) as session:
            published = False
            row = session.get(HarvestSource, source_id)
            if payload is not None:
                # the conditional GET of next time
                row.etag, row.last_modified = payload.etag, payload.last_modified
                if payload.sha256 != state.content_sha256:
                    _keep(session, source_id, payload)
                    published = harvester.store(session, source, payload)
                    row.content_sha256 = payload.sha256
                    row.last_change = _now()
            now = _now()
            row.last_success = now
            row.error_count = 0
            row.last_error = None
            row.next_run_at = next_run(
                harvester.policy, now, published, 0, random.random()
            )
            session.commit()
    except Exception as e:
        _record_error(harvester, source_id, e)


def prune_payloads():
    """Delete the payloads older than the retention (the job of every day)."""
    with Session(DBSession.get_bind()) as session:
        count = session.execute(
            delete(HarvestPayload).where(
                HarvestPayload.fetched_at < _now() - PAYLOAD_RETENTION
            )
        ).rowcount
        log.info('Pruning %d harvest payloads', count)
        session.commit()


def status(session):
    """Return the state of each harvester, for the health check."""
    rows = session.execute(
        select(
            HarvestSource.harvester,
            func.count(),
            func.count().filter(HarvestSource.error_count > 0),
            func.max(HarvestSource.last_success),
        ).group_by(HarvestSource.harvester)
    )
    return {
        name: {
            'sources': count,
            'failing': failing,
            'last_success': last_success.isoformat() if last_success else None,
        }
        for name, count, failing, last_success in rows
    }


def _keep(session, source_id, payload):
    # the same content seen before (A, B, then A again) is kept once
    session.execute(
        insert(HarvestPayload)
        .values(
            source_id=source_id,
            fetched_at=_now(),
            sha256=payload.sha256,
            content_type=payload.content_type,
            content=gzip.compress(payload.content),
        )
        .on_conflict_do_nothing(index_elements=['sha256'])
    )


def _record_error(harvester, source_id, error):
    log.warning('Harvesting %s failed: %r', source_id, error)
    try:
        with Session(DBSession.get_bind()) as session:
            row = session.get(HarvestSource, source_id)
            if row is None:
                # removed by a sync meanwhile
                return
            now = _now()
            row.error_count += 1
            row.last_error = repr(error)[:ERROR_LENGTH]
            row.next_run_at = next_run(
                harvester.policy, now, False, row.error_count, random.random()
            )
            session.commit()
    except Exception:
        # the lease brings the source back
        log.exception('Recording the error of %s failed', source_id)


def _host_slot(host):
    with _hosts_lock:
        return _hosts[host]


def _state_of(source):
    return State(
        source.etag, source.last_modified, source.content_sha256, source.state or {}
    )


def _now():
    return datetime.now(UTC)
