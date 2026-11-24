"""Run the harvesters: fetch the due sources, store and record the results."""

import gzip
import logging
import random
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import ProgrammingError
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
# the sources of the harvesters change with a deployment: checked this often
SYNC_EVERY = timedelta(minutes=10)
# a source no longer listed is kept this long (its history, if it comes back)
DISABLED_RETENTION = timedelta(days=30)
# what is kept of an error message
ERROR_LENGTH = 1000

# PostgreSQL's undefined_table: the migration of the harvest not run yet
UNDEFINED_TABLE = '42P01'

# the last sync of this process
_last_sync = None


def _jitter():
    """Return a number in [0, 1) that spreads the next runs of the sources."""
    # not a secret: only spreads the requests in time (Bandit B311)
    return random.random()  # nosec B311


def harvesters():
    """Return all the harvesters."""
    from c2corg_api.avalanche_bulletins.harvesters import (
        CaamlHarvester,
        MeteoFranceHarvester,
    )

    return [MeteoFranceHarvester(), CaamlHarvester()]


def harvest_enabled(settings, name=None):
    """Tell whether the scheduler harvests (`harvest.enabled`).

    For a harvester: `harvest.<name>.enabled`, else `harvest.enabled`.
    """
    value = settings.get('harvest.enabled', 'false')
    if name is not None:
        # empty (the .ini templates): as harvest.enabled
        value = str(settings.get(f'harvest.{name}.enabled', '')).strip() or value
    return str(value).strip().lower() in ('true', '1', 'yes', 'on')


def enabled_harvesters(settings):
    """Return the harvesters the settings switch on."""
    return [h for h in harvesters() if harvest_enabled(settings, h.name)]


def harvest_tick(settings=None, all_harvesters=None, workers=WORKERS):
    """Fetch the sources whose time has come (the job of every minute)."""
    global _last_sync
    if all_harvesters is None:
        all_harvesters = enabled_harvesters(settings or {})
    by_name = {h.name: h for h in all_harvesters}
    # A plain session on the engine configured on DBSession, as the other
    # jobs; each source then stores in its own session, in its thread.
    try:
        with Session(DBSession.get_bind()) as session:
            if _last_sync is None or _now() - _last_sync >= SYNC_EVERY:
                sync_sources(session, by_name.values())
                _last_sync = _now()
            claimed = claim(session, by_name)
    except ProgrammingError as e:
        if getattr(e.orig, 'pgcode', None) != UNDEFINED_TABLE:
            raise
        # deployed before `alembic upgrade head`: a line a minute, no trace
        log.warning('The harvest tables are missing (alembic upgrade head?)')
        return
    lanes = _lanes([(by_name[name], id, state) for name, id, state in claimed])
    if workers <= 1:
        for lane in lanes:
            _run_lane(lane)
        return
    with ThreadPoolExecutor(workers, thread_name_prefix='harvest') as executor:
        # run_source records its errors: nothing to collect
        list(executor.map(_run_lane, lanes))


def sync_sources(session, all_harvesters):
    """Add the new sources of the harvesters, disable the ones gone."""
    # a disabled source comes back with its state; deleted after a while
    now = _now()
    for harvester in all_harvesters:
        wanted = {harvester.source_id(source) for source in harvester.sources()}
        known = dict(
            session.execute(
                select(HarvestSource.id, HarvestSource.disabled_at).where(
                    HarvestSource.harvester == harvester.name
                )
            ).all()
        )
        if wanted - set(known):
            session.execute(
                insert(HarvestSource)
                .values(
                    [
                        {'id': id, 'harvester': harvester.name, 'next_run_at': now}
                        for id in sorted(wanted - set(known))
                    ]
                )
                .on_conflict_do_nothing()
            )
        back = [id for id in wanted & set(known) if known[id] is not None]
        gone = [id for id in set(known) - wanted if known[id] is None]
        if back:
            session.execute(
                update(HarvestSource)
                .where(HarvestSource.id.in_(back))
                .values(disabled_at=None, next_run_at=now)
            )
        if gone:
            session.execute(
                update(HarvestSource)
                .where(HarvestSource.id.in_(gone))
                .values(disabled_at=now)
            )
        session.execute(
            delete(HarvestSource).where(
                HarvestSource.harvester == harvester.name,
                HarvestSource.disabled_at < now - DISABLED_RETENTION,
            )
        )
    session.commit()


def claim(session, by_name, limit=CLAIMS):
    """Claim the due sources: (harvester name, source id, state), committed."""
    # SKIP LOCKED: the sources claimed meanwhile by another scheduler are left
    # to it; LEASE: the run of each source moves next_run_at again. A tick a
    # minute (never two at once): requests_per_minute bounds each tick.
    now = _now()
    claimed = []
    for name, harvester in by_name.items():
        count = min(limit - len(claimed), harvester.requests_per_minute or limit)
        if count <= 0:
            break
        sources = session.scalars(
            select(HarvestSource)
            .where(
                HarvestSource.harvester == name,
                HarvestSource.disabled_at.is_(None),
                HarvestSource.next_run_at <= now,
            )
            .order_by(HarvestSource.next_run_at)
            .limit(count)
            .with_for_update(skip_locked=True)
        ).all()
        for source in sources:
            source.next_run_at = now + LEASE
            source.last_attempt = now
            claimed.append((source.harvester, source.id, _state_of(source)))
    session.commit()
    return claimed


def run_source(harvester, source_id, state):
    """Fetch a source, store what is new, and record when to come back."""
    source = _source_of(harvester, source_id)
    try:
        payload = harvester.fetch(source, state)
    except NotModified:
        payload = None
    except Exception as e:
        _record_error(harvester, source_id, e)
        return
    try:
        with Session(DBSession.get_bind()) as session:
            row = session.get(HarvestSource, source_id)
            now = _now()
            if payload is not None:
                # the conditional GET of next time
                row.etag, row.last_modified = payload.etag, payload.last_modified
                if payload.sha256 != state.content_sha256:
                    if harvester.keep_payloads_days:
                        _keep(session, source_id, payload)
                    stored = harvester.store(session, source, payload)
                    if stored.state is not None:
                        row.state = stored.state
                    if stored.published:
                        row.last_publication = now
                    row.content_sha256 = payload.sha256
                    row.last_change = now
            row.last_success = now
            row.error_count = 0
            row.last_error = None
            row.next_run_at = next_run(
                harvester.policy, now, row.last_publication, 0, _jitter()
            )
            session.commit()
    except Exception as e:
        _record_error(harvester, source_id, e)


def prune_payloads(all_harvesters=None):
    """Delete the payloads older than their harvester keeps them (daily)."""
    with Session(DBSession.get_bind()) as session:
        count = 0
        for harvester in all_harvesters or harvesters():
            sources = select(HarvestSource.id).where(
                HarvestSource.harvester == harvester.name
            )
            before = _now() - timedelta(days=harvester.keep_payloads_days)
            count += session.execute(
                delete(HarvestPayload).where(
                    HarvestPayload.source_id.in_(sources),
                    HarvestPayload.fetched_at < before,
                )
            ).rowcount
        log.info('Pruning %d harvest payloads', count)
        session.commit()


def status(session, names=None):
    """Return the state of each harvester, for the health check."""
    # the enabled sources of the harvesters of this code (not of an older one)
    names = names or [h.name for h in harvesters()]
    rows = session.execute(
        select(
            HarvestSource.harvester,
            func.count(),
            func.count().filter(HarvestSource.error_count > 0),
            func.max(HarvestSource.last_success),
        )
        .where(HarvestSource.harvester.in_(names), HarvestSource.disabled_at.is_(None))
        .group_by(HarvestSource.harvester)
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
    # a content seen before (A, B, then A again) is kept once, as fetched now
    insertion = insert(HarvestPayload).values(
        source_id=source_id,
        fetched_at=_now(),
        sha256=payload.sha256,
        content_type=payload.content_type,
        content=gzip.compress(payload.content),
    )
    session.execute(
        insertion.on_conflict_do_update(
            constraint='uq_harvest_payloads_content',
            set_={'fetched_at': insertion.excluded.fetched_at},
        )
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
                harvester.policy,
                now,
                row.last_publication,
                row.error_count,
                _jitter(),
            )
            session.commit()
    except Exception:
        # the lease brings the source back
        log.exception('Recording the error of %s failed', source_id)


def _lanes(tasks):
    # PER_HOST lanes by host at most, each run in turn by a worker: a worker
    # never waits for a host busy with others
    by_host = {}
    for task in tasks:
        harvester, source_id, _ = task
        host = harvester.host(_source_of(harvester, source_id))
        by_host.setdefault(host, []).append(task)
    lanes = []
    for host_tasks in by_host.values():
        count = min(PER_HOST, len(host_tasks))
        lanes += [host_tasks[i::count] for i in range(count)]
    return lanes


def _run_lane(lane):
    for task in lane:
        run_source(*task)


def _source_of(harvester, source_id):
    return source_id.removeprefix(f'{harvester.name}:')


def _state_of(source):
    return State(
        source.etag, source.last_modified, source.content_sha256, source.state or {}
    )


def _now():
    return datetime.now(UTC)
