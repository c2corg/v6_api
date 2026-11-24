"""Harvest the outings reported on the partner sites (skitour.fr, gulliver.it...).

The adapters (`c2corg_api.partners`) are pure: this job gives them a transport
and a lookup cache, stores what they return in `guidebook.partner_outings`,
keeps the health of each source in `guidebook.partner_sources`, and purges the
outings older than the retention.
"""

import dataclasses
import logging
import os
import time
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, func, null, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from c2corg_api.models import DBSession, schema
from c2corg_api.models.partner_outing import (
    PartnerLookup,
    PartnerOuting,
    PartnerSource,
)
from c2corg_api.partners.adapter import (
    SourceBlocked,
    SourceDisabled,
    SourceDown,
)
from c2corg_api.partners.model import FetchContext
from c2corg_api.partners.sources import REGISTRY
from c2corg_api.partners.transport import FixtureTransport, HttpTransport

log = logging.getLogger(__name__)

BATCH_SIZE = 200
# days read on the first run of a source
INITIAL_DAYS = 14
# days re-read on each run: late lookups and edits get picked up
OVERLAP_DAYS = 2
# a run with more item errors than max(MIN_ITEM_ERRORS, 10% of the items) fails
MIN_ITEM_ERRORS = 3
MAX_ITEM_ERROR_RATIO = 0.1
# runs failed in a row before the backoff starts
BACKOFF_AFTER = 3
DETAIL_LENGTH = 500
DEFAULT_FIXTURES_DIR = (
    Path(__file__).resolve().parent.parent / 'tests' / ('partners/fixtures')
)

# the statuses that count as a failed run (the backoff and the failure counter)
FAILURE_STATUSES = ('blocked', 'down', 'failing')


def _setting_is_true(settings, key):
    return str(settings.get(key, 'false')).strip().lower() in ('true', '1', 'yes', 'on')


def partners_enabled(settings):
    """Tell whether the scheduler harvests the partner outings."""
    return _setting_is_true(settings, 'partners.enabled')


def enabled_sources(settings):
    """Return the configured sources that have an adapter (`partners.sources`)."""
    names = [
        name.strip()
        for name in str(settings.get('partners.sources', '')).split(',')
        if name.strip()
    ]
    sources = []
    for name in names:
        if name not in REGISTRY:
            log.warning('Partner source %s has no adapter, skipped', name)
        elif name not in sources:
            sources.append(name)
    return sources


def _retention_days(settings):
    return int(settings.get('partners.retention_days') or 31)


def _interval_minutes(settings):
    return int(settings.get('partners.interval_minutes') or 15)


def transport_for(adapter_cls, settings):
    """Return the transport of an adapter: the real site or the fixtures."""
    kind = str(settings.get('partners.transport') or 'http').strip().lower()
    if kind == 'http':
        return HttpTransport(adapter_cls.rate)
    if kind == 'fixtures':
        directory = settings.get('partners.fixtures_dir') or DEFAULT_FIXTURES_DIR
        return FixtureTransport(
            Path(directory), adapter_cls.name, rate=adapter_cls.rate
        )
    raise ValueError(f'Unknown partners.transport: {kind}')


class DbLookupCache:
    """A `LookupCache` kept in `guidebook.partner_lookups`, per source.

    It does not commit: the lookups are committed with the run of the source.
    """

    def __init__(self, session, source):
        self.session = session
        self.source = source

    def get(self, key):
        return self.session.scalar(
            select(PartnerLookup.data).where(
                PartnerLookup.source == self.source, PartnerLookup.key == key
            )
        )

    def put(self, key, data):
        statement = insert(PartnerLookup).values(
            source=self.source, key=key, data=data, fetched_at=func.now()
        )
        self.session.execute(
            statement.on_conflict_do_update(
                index_elements=['source', 'key'],
                set_={'data': statement.excluded.data, 'fetched_at': func.now()},
            )
        )


def _outing_values(outing, now):
    if outing.lon is not None and outing.lat is not None:
        geom = func.ST_Transform(
            func.ST_SetSRID(func.ST_MakePoint(outing.lon, outing.lat), 4326), 3857
        )
    else:
        geom = null()
    return {
        'source': outing.source,
        'external_id': outing.external_id,
        'url': outing.url,
        'title': outing.title,
        'lang': outing.lang,
        'date': outing.date,
        'author': outing.author,
        'author_url': outing.author_url,
        'region': outing.region,
        'activities': list(outing.activities),
        'source_activity': outing.source_activity,
        'ski_rating_min': outing.ski_rating_min,
        'ski_rating_max': outing.ski_rating_max,
        'rating_raw': outing.rating_raw,
        'rating_system': outing.rating_system,
        'steep': outing.steep,
        'elevation_max': outing.elevation_max,
        'height_diff_up': outing.height_diff_up,
        'orientations': list(outing.orientations) or None,
        'snow': dict(outing.snow) if outing.snow else None,
        'geom': geom,
        'geom_quality': outing.geom_quality,
        # recomputed by assign_areas
        'area_ids': [],
        'fetched_at': now,
    }


def upsert_outings(session, outings, now):
    """Insert or update the outings, and return their ids.

    One row per (source, external_id): an outing already known is updated,
    keeping its id and `first_seen_at`. Does not commit.
    """
    # one statement cannot update a row twice: the last occurrence wins
    unique = {(o.source, o.external_id): o for o in outings}
    outings = list(unique.values())
    ids = []
    for start in range(0, len(outings), BATCH_SIZE):
        rows = [_outing_values(o, now) for o in outings[start : start + BATCH_SIZE]]
        statement = insert(PartnerOuting).values(rows)
        keep = {'id', 'first_seen_at', 'source', 'external_id'}
        update = {
            column.name: statement.excluded[column.name]
            for column in PartnerOuting.__table__.columns
            if column.name not in keep
        }
        statement = statement.on_conflict_do_update(
            constraint='uq_partner_outings_source_external_id', set_=update
        ).returning(PartnerOuting.id)
        ids.extend(session.execute(statement).scalars().all())
    return ids


def assign_areas(session, ids=None):
    """Set `area_ids` to the areas containing the point of the outings.

    All the outings when `ids` is None. Redirected areas are ignored. Does not
    commit.
    """
    # ST_Intersects: the predicate of area_association.update_areas_for_document
    sql = f"""
        UPDATE {schema}.partner_outings p SET area_ids = COALESCE((
            SELECT array_agg(g.document_id ORDER BY g.document_id)
            FROM {schema}.documents_geometries g
            JOIN {schema}.areas a ON a.document_id = g.document_id
            JOIN {schema}.documents d
              ON d.document_id = a.document_id AND d.redirects_to IS NULL
            WHERE ST_Intersects(g.geom_detail, p.geom)), '{{}}')
        WHERE p.geom IS NOT NULL"""
    if ids is None:
        session.execute(text(sql))
    elif ids:
        session.execute(text(sql + ' AND p.id = ANY(:ids)'), {'ids': list(ids)})


def purge_partner_outings(session, now, retention_days):
    """Delete the outings older than the retention, and return their number.

    The areas get edited: the areas of the remaining outings are recomputed.
    Does not commit.
    """
    limit = now.date() - timedelta(days=retention_days)
    deleted = session.execute(
        delete(PartnerOuting).where(PartnerOuting.date < limit)
    ).rowcount
    assign_areas(session)
    log.info('Deleted %d partner outings older than %s', deleted, limit)
    return deleted


def _clean_detail(message, secrets):
    for value in secrets.values():
        if value:
            message = message.replace(value, '***')
    return message[:DETAIL_LENGTH]


def _get_source_row(session, name):
    row = session.get(PartnerSource, name)
    if row is None:
        row = PartnerSource(
            source=name,
            status='never_run',
            consecutive_failures=0,
            last_skipped={},
        )
        session.add(row)
    return row


def _backoff_active(row, now, settings):
    """Tell whether a source failing in a row is left alone for a while."""
    failures = row.consecutive_failures or 0
    if failures < BACKOFF_AFTER or row.last_run_at is None:
        return False
    wait = timedelta(minutes=_interval_minutes(settings) * 2 ** min(failures - 2, 4))
    return now - row.last_run_at < wait


def _since(row, now, settings):
    last_success = row.last_success_at or now - timedelta(days=INITIAL_DAYS)
    last_success = last_success.astimezone(UTC)
    return max(
        now.date() - timedelta(days=_retention_days(settings)),
        last_success.date() - timedelta(days=OVERLAP_DAYS),
    )


def _secrets(adapter, fixtures):
    if fixtures:
        return {name: 'fixture' for name in adapter.required_secrets}
    values = {name: os.getenv(name) for name in adapter.required_secrets}
    return {name: value for name, value in values.items() if value}


def run_source(session, adapter, transport, lookups, now, settings):
    """Harvest one source and record its health. Never raises.

    Commits (the outings, the lookups and the health of the source are one
    unit; a failure never touches the other sources). Returns the status.
    """
    name = adapter.name
    try:
        row = _get_source_row(session, name)
        if _backoff_active(row, now, settings):
            log.info('Partner source %s is in backoff, skipped', name)
            session.rollback()
            return row.status
        return _run_source(session, row, adapter, transport, lookups, now, settings)
    except Exception:
        # the health itself could not be recorded (database error...)
        log.exception('Partner source %s: the run crashed', name)
        try:
            session.rollback()
        except Exception:
            log.exception('Partner source %s: rollback failed', name)
        return 'failing'


def _run_source(session, row, adapter, transport, lookups, now, settings):
    name = adapter.name
    fixtures = isinstance(transport, FixtureTransport)
    secrets = _secrets(adapter, fixtures)
    started = time.monotonic()
    row.last_run_at = now
    status = 'ok'
    detail = None
    result = None
    upserted = 0
    skipped = Counter()
    fetched = 0
    try:
        ctx = FetchContext(
            since=_since(row, now, settings),
            now=now,
            cursor=row.cursor,
            transport=transport,
            lookups=lookups,
            secrets=secrets,
        )
        result = adapter.fetch(ctx)
    except SourceDisabled as e:
        status, detail = 'disabled', str(e)
    except SourceBlocked as e:
        status, detail = 'blocked', str(e)
    except SourceDown as e:
        status, detail = 'down', str(e)
    except SQLAlchemyError as e:
        # the transaction is unusable: the lookups of this run are lost
        session.rollback()
        row = _get_source_row(session, name)
        row.last_run_at = now
        status, detail = 'failing', f'{type(e).__name__}: {e}'
    except Exception as e:
        log.warning('Partner source %s failed', name, exc_info=True)
        status, detail = 'failing', f'{type(e).__name__}: {e}'

    if result is not None:
        seen = len(result.outings) + result.item_errors
        fetched = len(result.outings)
        skipped = Counter(result.skipped)
        if result.item_errors > max(MIN_ITEM_ERRORS, MAX_ITEM_ERROR_RATIO * seen):
            status = 'failing'
            detail = f'{result.item_errors} items failed to parse out of {seen}'
        else:
            if result.item_errors:
                status = 'degraded'
                detail = f'{result.item_errors} items failed to parse'
            try:
                upserted = _store(
                    session, name, result, transport, now, settings, skipped
                )
            except Exception as e:
                log.warning('Partner source %s: storing failed', name, exc_info=True)
                session.rollback()
                row = _get_source_row(session, name)
                row.last_run_at = now
                status, detail = 'failing', f'{type(e).__name__}: {e}'
                upserted = 0
            else:
                row.cursor = result.cursor if result.cursor is not None else null()

    row.status = status
    row.status_detail = _clean_detail(detail, secrets) if detail else None
    row.last_duration_ms = int((time.monotonic() - started) * 1000)
    row.last_requests = transport.request_count
    row.last_fetched = fetched
    row.last_upserted = upserted
    row.last_skipped = dict(skipped)
    if status in ('ok', 'degraded'):
        row.last_success_at = now
        row.consecutive_failures = 0
    elif status in FAILURE_STATUSES:
        row.last_error_at = now
        row.consecutive_failures = (row.consecutive_failures or 0) + 1
    else:
        # disabled: a choice, not a failure
        row.consecutive_failures = 0
    session.commit()
    log.info('Partner source %s: %s (%d upserted)', name, status, upserted)
    return status


def _store(session, name, result, transport, now, settings, skipped):
    """Upsert the outings of a result, and assign their areas."""
    outings = result.outings
    if isinstance(transport, FixtureTransport) and transport.recorded_at:
        shift = now.date() - date.fromisoformat(transport.recorded_at)
        log.warning(
            'Partner source %s: fixtures, dates shifted by %d days', name, shift.days
        )
        outings = [dataclasses.replace(o, date=o.date + shift) for o in outings]
    limit = now.date() - timedelta(days=_retention_days(settings))
    kept = [o for o in outings if o.date >= limit]
    if len(kept) < len(outings):
        skipped['too_old'] += len(outings) - len(kept)
    ids = upsert_outings(session, kept, now)
    assign_areas(session, ids)
    return len(ids)


def harvest_partner_outings(settings, now=None):
    """Run the adapters of the enabled sources, one after the other.

    The entry point of the scheduler. A source failing never stops the next
    one. The outings older than the retention are purged by their own job.
    """
    now = now or datetime.now(UTC)
    # a savepoint per commit when the bind is a connection already in a
    # transaction (the tests), nothing special on the engine
    with Session(
        DBSession.get_bind(), join_transaction_mode='create_savepoint'
    ) as session:
        for name in enabled_sources(settings):
            try:
                adapter_cls = REGISTRY[name]
                transport = transport_for(adapter_cls, settings)
                run_source(
                    session,
                    adapter_cls(),
                    transport,
                    DbLookupCache(session, name),
                    now,
                    settings,
                )
            except Exception as e:
                log.exception('Partner source %s could not start', name)
                _record_failure(session, name, now, e)


def _record_failure(session, name, now, error):
    try:
        session.rollback()
        row = _get_source_row(session, name)
        row.status = 'failing'
        row.status_detail = f'{type(error).__name__}: {error}'[:DETAIL_LENGTH]
        row.last_run_at = row.last_error_at = now
        row.consecutive_failures = (row.consecutive_failures or 0) + 1
        session.commit()
    except Exception:
        log.exception('Partner source %s: health not recorded', name)
        session.rollback()


def purge_partner_outings_job(settings):
    """Scheduler entry point: purge the old outings, recompute the areas."""
    now = datetime.now(UTC)
    with Session(
        DBSession.get_bind(), join_transaction_mode='create_savepoint'
    ) as session:
        purge_partner_outings(session, now, _retention_days(settings))
        session.commit()
