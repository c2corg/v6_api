"""Harvest the outings reported on the partner sites (skitour.fr, gulliver.it...).

The adapters (`c2corg_api.partners`) are pure: this job gives them a transport
and a lookup cache, stores what they return in `guidebook.partner_outings`,
keeps the health of each source in `guidebook.partner_sources`, and purges the
lookups older than their retention (and the outings older than theirs, when one
is set: by default the outings are kept forever).

Each adapter is a harvester of `c2corg_api.harvest` (`PartnerHarvester`,
named `partners.<adapter>`): the harvest tick schedules it, switches it on
(`harvest.partners.enabled`, `harvest.partners.<adapter>.enabled`), backs off
after errors and reports it in the health check, as the other harvesters.
"""

import dataclasses
import json
import logging
import os
import time
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote, quote_plus

from sqlalchemy import delete, func, null, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from c2corg_api.harvest.harvester import Harvester, Payload, Stored
from c2corg_api.harvest.policy import Policy
from c2corg_api.jobs.partner_locations import resolve_locations
from c2corg_api.jobs.partner_tracks import harvest_tracks, track_transport
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
DETAIL_LENGTH = 500
NOT_CONFIGURED = 'not configured'
HARVESTER_PREFIX = 'partners.'
# the one source of a partner harvester: `partners.skitour:outings`
OUTINGS = 'outings'
# the run summaries kept in harvest_payloads (small JSON), for debugging
KEEP_SUMMARIES_DAYS = 7
DEFAULT_FIXTURES_DIR = (
    Path(__file__).resolve().parent.parent / 'tests' / ('partners/fixtures')
)

# the statuses that count as a failed run (the backoff and the failure counter)
FAILURE_STATUSES = ('blocked', 'down', 'failing')


def _setting_is_true(settings, key):
    return str(settings.get(key, 'false')).strip().lower() in ('true', '1', 'yes', 'on')


def harvester_name(source):
    """Return the name of the harvester of a partner source: `partners.<source>`."""
    return f'{HARVESTER_PREFIX}{source}'


def enabled_sources(settings):
    """Return the partner sources switched on (`harvest.partners[.<name>].enabled`)."""
    from c2corg_api.harvest.runner import harvest_enabled

    return [
        name for name in REGISTRY if harvest_enabled(settings, harvester_name(name))
    ]


def partners_enabled(settings):
    """Tell whether the scheduler harvests at least one partner source."""
    return bool(enabled_sources(settings))


def _retention_days(settings):
    """Days an outing is kept; None (empty or 0, the default): forever.

    The API only ever lists a window of 31 days at most: the older rows are
    kept for later uses (statistics, a backfill...), not served.
    """
    value = str(settings.get('partners.retention_days') or '').strip()
    days = int(value) if value else 0
    return days if days > 0 else None


def _lookup_retention_days(settings):
    return int(settings.get('partners.lookup_retention_days') or 30)


def synthetic_allowed(settings):
    """Tell whether fixture mode may run on synthetic (hand-made) fixtures."""
    return _setting_is_true(settings, 'partners.allow_synthetic')


class SyntheticFixtures(Exception):
    """Fixture mode on a synthetic manifest, where that is not allowed."""


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


def _outing_values(outing, now, area_ids=None):
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
        'gpx_url': outing.gpx_url,
        'texts': dict(outing.texts) if outing.texts else None,
        'geom': geom,
        'geom_quality': outing.geom_quality,
        # recomputed by assign_areas from the point, unless given (the outings
        # located by their region or country: see partner_locations)
        'area_ids': list(area_ids or []),
        'fetched_at': now,
    }


def upsert_outings(session, outings, now, area_ids=None):
    """Insert or update the outings, and return their ids.

    One row per (source, external_id): an outing already known is updated,
    keeping its id and `first_seen_at`. `area_ids` gives the areas of some
    outings, by `(source, external_id)`; the others get theirs from
    `assign_areas`. Does not commit.
    """
    area_ids = area_ids or {}
    # one statement cannot update a row twice: the last occurrence wins
    unique = {(o.source, o.external_id): o for o in outings}
    outings = list(unique.values())
    ids = []
    for start in range(0, len(outings), BATCH_SIZE):
        rows = [
            _outing_values(o, now, area_ids.get((o.source, o.external_id)))
            for o in outings[start : start + BATCH_SIZE]
        ]
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

    All the outings when `ids` is None. Redirected areas are ignored. The
    outings placed at the centroid of their region keep the areas of the
    region (`partner_locations`): the centroid is not where they are. Does not
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
        WHERE p.geom IS NOT NULL AND p.geom_quality <> 'area_centroid'"""  # nosec B608 (constant SQL)
    if ids is None:
        session.execute(text(sql))
    elif ids:
        session.execute(text(sql + ' AND p.id = ANY(:ids)'), {'ids': list(ids)})


def purge_partner_outings(session, now, retention_days):
    """Delete the outings older than the retention, and return their number.

    `retention_days` None: no retention, nothing deleted. The areas get
    edited: the areas of the remaining outings are recomputed. Does not commit.
    """
    if retention_days is None:
        return 0
    limit = now.date() - timedelta(days=retention_days)
    deleted = session.execute(
        delete(PartnerOuting).where(PartnerOuting.date < limit)
    ).rowcount
    assign_areas(session)
    log.info('Deleted %d partner outings older than %s', deleted, limit)
    return deleted


def purge_partner_lookups(session, now, retention_days):
    """Delete the lookups not fetched for `retention_days`; return their number.

    Does not commit.
    """
    limit = now - timedelta(days=retention_days)
    deleted = session.execute(
        delete(PartnerLookup).where(PartnerLookup.fetched_at < limit)
    ).rowcount
    log.info('Deleted %d partner lookups older than %s', deleted, limit.date())
    return deleted


def _clean_detail(message, secrets):
    # also the forms a secret takes in a URL (an error often quotes the URL)
    forms = {
        form
        for value in secrets.values()
        if value
        for form in (value, quote(value, safe=''), quote_plus(value))
    }
    for form in sorted(forms, key=len, reverse=True):
        message = message.replace(form, '***')
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


def _since(row, now, settings):
    last_success = row.last_success_at or now - timedelta(days=INITIAL_DAYS)
    last_success = last_success.astimezone(UTC)
    since = last_success.date() - timedelta(days=OVERLAP_DAYS)
    retention = _retention_days(settings)
    if retention is None:
        return since
    return max(now.date() - timedelta(days=retention), since)


def _secret(name):
    """Return a secret: `$NAME`, else the content of the file `$NAME_FILE`.

    The `*_FILE` form is the one of Docker secrets (`/run/secrets/...`).
    """
    value = os.getenv(name)
    if value:
        return value
    path = os.getenv(f'{name}_FILE')
    if not path:
        return None
    try:
        return Path(path).read_text(encoding='utf-8').strip() or None
    except OSError as e:
        # Neither the name nor the path: CodeQL counts both as secret data.
        log.warning('Cannot read a partner secret file: %s', type(e).__name__)
        return None


def _secrets(adapter, fixtures):
    if fixtures:
        return {name: 'fixture' for name in adapter.required_secrets}
    values = {name: _secret(name) for name in adapter.required_secrets}
    return {name: value for name, value in values.items() if value}


def run_source(session, adapter, transport, lookups, now, settings):
    """Harvest one source and record its health. Never raises.

    Commits (the outings, the lookups and the health of the source are one
    unit; a failure never touches the other sources). Returns the status. The
    backoff after failures is the harvest policy's (`PartnerHarvester`).
    """
    name = adapter.name
    try:
        row = _get_source_row(session, name)
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
    shift = _fixture_shift(name, transport, now)
    try:
        if fixtures and transport.synthetic and not synthetic_allowed(settings):
            raise SyntheticFixtures(
                f'the fixtures of {name} are synthetic and partners.allow_synthetic'
                ' is not true: refused, nothing stored'
            )
        # in fixture mode the adapter lives on the day of the recording: its
        # `since` filter and relative dates ("yesterday") match the fixtures
        ctx = FetchContext(
            since=_since(row, now, settings) - shift,
            now=now - shift,
            cursor=row.cursor,
            transport=transport,
            lookups=lookups,
            secrets=secrets,
        )
        result = adapter.fetch(ctx)
    except SyntheticFixtures as e:
        log.error('Partner source %s: %s', name, e)
        status, detail = 'failing', str(e)
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
            problems = []
            if result.item_errors:
                problems.append(f'{result.item_errors} items failed to parse')
            if skipped['lookup_failed']:
                # detail pages, routes...: those outings keep their hints only
                problems.append(f'{skipped["lookup_failed"]} lookups failed')
            if problems:
                status = 'degraded'
                detail = ', '.join(problems)
            try:
                upserted = _store(
                    session, result, shift, now, settings, skipped, lookups
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
    # the fixture secrets are placeholders, not worth masking ("No fixture...")
    masked = {} if fixtures else secrets
    row.status_detail = _clean_detail(detail, masked) if detail else None
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


def _fixture_shift(name, transport, now):
    """Return the days between the recording of the fixtures and today.

    Zero in http mode. The demo shows the fixtures as if recorded today.
    """
    if not isinstance(transport, FixtureTransport) or not transport.recorded_at:
        return timedelta(0)
    shift = now.date() - date.fromisoformat(transport.recorded_at)
    log.warning(
        'Partner source %s: fixtures, dates shifted by %d days', name, shift.days
    )
    return shift


def _store(session, result, shift, now, settings, skipped, lookups):
    """Locate the outings without coordinates, upsert them, assign their areas."""
    outings = result.outings
    if shift:
        outings = [dataclasses.replace(o, date=o.date + shift) for o in outings]
    retention = _retention_days(settings)
    if retention is None:
        kept = list(outings)
    else:
        limit = now.date() - timedelta(days=retention)
        kept = [o for o in outings if o.date >= limit]
    if len(kept) < len(outings):
        skipped['too_old'] += len(outings) - len(kept)
    kept, area_ids, located = resolve_locations(session, lookups, kept)
    if located:
        log.info('Partner outings located from their hints: %s', dict(located))
    ids = upsert_outings(session, kept, now, area_ids)
    assign_areas(session, ids)
    return len(ids)


class PartnerRunFailed(Exception):
    """A run ended `blocked`, `down` or `failing`: an error of its harvest source.

    The message is the status and its detail, the secrets masked.
    """


class PartnerHarvester(Harvester):
    """The harvester of one partner source (`partners.skitour:outings`).

    An adapter pages, and looks things up in the database while it fetches:
    no one-URL payload to store later. So `fetch` runs the whole source
    (`run_source`: the adapter, the outings, the health in partner_sources,
    committed together), and hands the runner a summary of the run (the
    payload kept, `store` a no-op). A failed run raises `PartnerRunFailed`:
    the runner records the error and backs off (`policy`).
    """

    keep_payloads_days = KEEP_SUMMARIES_DAYS

    def __init__(self, adapter_cls, settings=None, clock=None):
        self.adapter_cls = adapter_cls
        self.settings = settings or {}
        self.name = harvester_name(adapter_cls.name)
        every = _interval_minutes(self.settings)
        # every `partners.interval_minutes`; after errors, from the same
        # interval, doubled up to 16 times it
        self.policy = Policy(
            default_every=every,
            after_publication_every=None,
            backoff_min=every,
            backoff_max=every * 16,
        )
        self._clock = clock or (lambda: datetime.now(UTC))

    def sources(self):
        return [OUTINGS]

    def url(self, source):
        # its host: the lanes of the runner, one site at a time
        return self.adapter_cls.site_url

    def fetch(self, source, state):
        name = self.adapter_cls.name
        now = self._clock()
        # a savepoint per commit when the bind is a connection already in a
        # transaction (the tests), nothing special on the engine
        with Session(
            DBSession.get_bind(), join_transaction_mode='create_savepoint'
        ) as session:
            try:
                transport = transport_for(self.adapter_cls, self.settings)
                adapter = self.adapter_cls()
            except Exception as e:
                log.exception('Partner source %s could not start', name)
                _record_failure(session, name, now, e, _start_secrets(name))
                raise PartnerRunFailed(f'failing: {type(e).__name__}') from e
            status = run_source(
                session,
                adapter,
                transport,
                DbLookupCache(session, name),
                now,
                self.settings,
            )
            session.expire_all()
            row = session.get(PartnerSource, name)
            summary = {
                'status': status,
                'status_detail': row.status_detail if row else None,
                'fetched': row.last_fetched if row else None,
                'upserted': row.last_upserted if row else None,
                'skipped': (row.last_skipped or {}) if row else {},
            }
            if status in ('ok', 'degraded'):
                tracks = self._tracks(session, now)
                if tracks is not None:
                    summary['tracks'] = tracks
        if status in FAILURE_STATUSES:
            raise PartnerRunFailed(f'{status}: {summary["status_detail"]}')
        return Payload(json.dumps(summary, sort_keys=True).encode(), 'application/json')

    def _tracks(self, session, now):
        """Run the second phase: a few GPX tracks (partner_tracks). Never raises."""
        try:
            directory = self.settings.get('partners.fixtures_dir') or (
                DEFAULT_FIXTURES_DIR
            )
            transport = track_transport(self.adapter_cls, self.settings, directory)
            if transport is None:
                return None
            return harvest_tracks(
                session, self.adapter_cls, transport, now, self.settings
            )
        except Exception:
            log.exception('Partner tracks %s failed', self.adapter_cls.name)
            session.rollback()
            return None

    def store(self, session, source, payload):
        # stored by fetch; a run that wrote outings is a publication
        summary = json.loads(payload.content)
        return Stored(published=bool(summary.get('upserted')))


def partner_harvesters(settings=None, clock=None):
    """Return a harvester for each partner adapter (`harvest.runner.harvesters`)."""
    return [PartnerHarvester(REGISTRY[name], settings, clock) for name in REGISTRY]


def harvest_partner_outings(settings, now=None):
    """Harvest the enabled partner sources once, now (make harvest-partners).

    The scheduler runs them through the harvest tick instead. A source failing
    never stops the next one. The outings older than the retention are purged
    by their own job.
    """
    from c2corg_api.harvest.runner import harvest_now

    clock = (lambda: now) if now is not None else None
    enabled = set(enabled_sources(settings))
    harvest_now(
        [
            h
            for h in partner_harvesters(settings, clock)
            if h.adapter_cls.name in enabled
        ]
    )
    mark_unconfigured_sources(settings)


def _start_secrets(name):
    adapter_cls = REGISTRY.get(name)
    return _secrets(adapter_cls, False) if adapter_cls else {}


def _mark_unconfigured(session, configured):
    """Mark the sources not switched on (`harvest.partners...`) as `disabled`.

    Their outings stay stored (forever, unless a retention is set). Never raises.
    """
    try:
        names = set(REGISTRY) | set(session.scalars(select(PartnerSource.source)))
        for name in sorted(names - set(configured)):
            row = _get_source_row(session, name)
            row.status = 'disabled'
            row.status_detail = NOT_CONFIGURED
            row.consecutive_failures = 0
        session.commit()
    except Exception:
        log.exception('Partner sources: the unconfigured ones were not marked')
        session.rollback()


def mark_unconfigured_sources(settings):
    """Scheduler entry point: mark the sources switched off as `disabled`.

    Run when the scheduler starts (the switches only change with a restart),
    and by `harvest_partner_outings`.
    """
    with Session(
        DBSession.get_bind(), join_transaction_mode='create_savepoint'
    ) as session:
        _mark_unconfigured(session, enabled_sources(settings))


def _record_failure(session, name, now, error, secrets=None):
    try:
        session.rollback()
        row = _get_source_row(session, name)
        row.status = 'failing'
        row.status_detail = _clean_detail(
            f'{type(error).__name__}: {error}', secrets or {}
        )
        row.last_run_at = row.last_error_at = now
        row.consecutive_failures = (row.consecutive_failures or 0) + 1
        session.commit()
    except Exception:
        log.exception('Partner source %s: health not recorded', name)
        session.rollback()


def purge_partner_outings_job(settings):
    """Scheduler entry point: purge the old outings and lookups.

    Scheduled even when the harvest is off: the rows must not outlive the
    retention, when one is set (`partners.retention_days`; empty: the outings
    are kept forever, only the lookups are purged).
    """
    now = datetime.now(UTC)
    with Session(
        DBSession.get_bind(), join_transaction_mode='create_savepoint'
    ) as session:
        purge_partner_outings(session, now, _retention_days(settings))
        purge_partner_lookups(session, now, _lookup_retention_days(settings))
        session.commit()
