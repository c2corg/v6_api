"""TEMPORARY: backfill the older outings of the partner sites (c2corg/v6_api#2763).

Delete with the other `backfill_*` files once the history is imported.

The harvest (`harvest_partner_outings`) reads the latest reports of each site.
This job walks the older ones, a step at a time: a step reads a few pages of a
source (`partners/backfill_sources.py`), stores their outings exactly as the
harvest does (`_store`: locations, upsert by source and external id, areas;
the lookups in the same cache), and saves where it stopped in
`guidebook.backfill_partner_states`, committed with the outings. A step that
fails stores nothing and keeps the cursor: the next step tries again.

It never touches the state of the harvest: no `partner_sources` (the health of
`/partner-outings/sources`), no `harvest_sources` (schedule, back-off, `/health`).

Run it by hand (`make backfill-partners`, `scripts/jobs/backfill_partners.py`)
or let the scheduler run a step of each source every hour: set
`PARTNERS_BACKFILL_SOURCES` (`all`, or `skitour,bivouak`...) in the environment
of the scheduler. The sources switched off for the harvest are never
backfilled (unless `--force` by hand).
"""

import datetime
import logging
import os
from collections import Counter
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from c2corg_api.jobs.harvest_partner_outings import (
    MAX_ITEM_ERROR_RATIO,
    MIN_ITEM_ERRORS,
    DbLookupCache,
    _clean_detail,
    _fixture_shift,
    _secrets,
    _store,
    enabled_sources,
    synthetic_allowed,
)
from c2corg_api.models import DBSession
from c2corg_api.models.backfill_partner_state import BackfillPartnerState
from c2corg_api.partners.adapter import (
    ParseError,
    SourceBlocked,
    SourceDisabled,
    SourceDown,
)
from c2corg_api.partners.backfill_sources import BACKFILLERS, season_of
from c2corg_api.partners.backfill_transport import (
    BackfillFixtureTransport,
    BackfillHttpTransport,
)
from c2corg_api.partners.model import FetchContext, RateLimit
from c2corg_api.partners.sources import REGISTRY
from c2corg_api.partners.transport import FixtureTransport

log = logging.getLogger(__name__)

# the default floor: the start of the season 5 seasons ago (2022-09-01 in
# November 2026)
DEFAULT_SEASONS = 5
DEFAULT_EVERY_MINUTES = 60
DEFAULT_FIXTURES_DIR = (
    Path(__file__).resolve().parent.parent / 'tests' / 'partners' / 'backfill_fixtures'
)
# settings key, else environment variable
SOURCES_OPTION = ('partners.backfill.sources', 'PARTNERS_BACKFILL_SOURCES')
FLOOR_OPTION = ('partners.backfill.floor', 'PARTNERS_BACKFILL_FLOOR')
EVERY_OPTION = ('partners.backfill.every_minutes', 'PARTNERS_BACKFILL_EVERY_MINUTES')


def _option(settings, option):
    key, env = option
    value = settings.get(key)
    if value is None or str(value).strip() == '':
        value = os.getenv(env, '')
    return str(value).strip()


def default_floor(today):
    """Return the start of the season `DEFAULT_SEASONS` seasons ago."""
    return datetime.date(season_of(today) - DEFAULT_SEASONS, 9, 1)


def configured_floor(settings, today):
    value = _option(settings, FLOOR_OPTION)
    return datetime.date.fromisoformat(value) if value else default_floor(today)


def backfill_sources(settings, requested=None, force=False):
    """Return the sources to backfill: asked (or configured), and switched on.

    `requested`: names, or `['all']`; None reads `PARTNERS_BACKFILL_SOURCES`.
    The sources switched off for the harvest are left out, unless `force`.
    """
    if requested is None:
        requested = [s for s in _option(settings, SOURCES_OPTION).split(',') if s]
    requested = [s.strip() for s in requested if s.strip()]
    if 'all' in requested:
        requested = list(BACKFILLERS)
    unknown = sorted(set(requested) - set(BACKFILLERS))
    if unknown:
        raise ValueError(f'unknown partner sources: {", ".join(unknown)}')
    allowed = set(BACKFILLERS) if force else set(enabled_sources(settings))
    return [name for name in BACKFILLERS if name in requested and name in allowed]


def backfill_transport(name, settings, requests):
    """Return the transport of a step: the site, or the backfill fixtures."""
    adapter_cls = REGISTRY[name]
    rate = RateLimit(
        adapter_cls.rate.min_interval_s, requests, adapter_cls.rate.timeout_s
    )
    kind = str(settings.get('partners.transport') or 'http').strip().lower()
    if kind == 'http':
        return BackfillHttpTransport(rate)
    if kind == 'fixtures':
        directory = settings.get('partners.backfill.fixtures_dir') or (
            DEFAULT_FIXTURES_DIR
        )
        return BackfillFixtureTransport(Path(directory), name, rate=rate)
    raise ValueError(f'Unknown partners.transport: {kind}')


def _locked_state(session, name):
    """Return the state row of a source, locked; None when another step holds it."""
    session.execute(
        insert(BackfillPartnerState).values(source=name).on_conflict_do_nothing()
    )
    # committed apart: a step that fails rolls back to a row that exists
    session.commit()
    return session.scalars(
        select(BackfillPartnerState)
        .where(BackfillPartnerState.source == name)
        .with_for_update(skip_locked=True)
    ).one_or_none()


def backfill_source(
    session, name, settings, now, floor, pages=None, details=None, transport=None
):
    """Run one step of the backfill of a source; return its summary. Commits.

    The summary: `status` (`ok`, `degraded`, `done` when there was nothing
    left, `busy` when another step holds the source, or the failure:
    `disabled`, `blocked`, `down`, `failing`), `detail`, `fetched`,
    `upserted`, `requests`, `cursor`.
    """
    backfiller = BACKFILLERS[name]()
    adapter_cls = REGISTRY[name]
    pages = pages or backfiller.pages_per_run
    details = backfiller.details_per_run if details is None else details
    summary = {'source': name, 'fetched': 0, 'upserted': 0, 'requests': 0}

    state = _locked_state(session, name)
    if state is None:
        session.rollback()
        return {**summary, 'status': 'busy', 'detail': 'another step runs'}
    if state.cursor and state.cursor.get('done'):
        session.commit()
        return {**summary, 'status': 'done', 'cursor': state.cursor}

    if transport is None:
        transport = backfill_transport(
            name, settings, backfiller.requests(pages, details)
        )
    fixtures = isinstance(transport, FixtureTransport)
    secrets = _secrets(adapter_cls, fixtures)
    shift = _fixture_shift(name, transport, now)
    lookups = DbLookupCache(session, name)
    status, detail, result = 'ok', None, None
    try:
        if fixtures and transport.synthetic and not synthetic_allowed(settings):
            raise SourceDisabled(
                'synthetic fixtures and partners.allow_synthetic is not true'
            )
        ctx = FetchContext(
            since=floor - shift,
            now=now - shift,
            cursor=state.cursor,
            transport=transport,
            lookups=lookups,
            secrets=secrets,
        )
        result = backfiller.step(ctx, pages, details)
    except SourceDisabled as e:
        status, detail = 'disabled', str(e)
    except SourceBlocked as e:
        status, detail = 'blocked', str(e)
    except SourceDown as e:
        status, detail = 'down', str(e)
    except ParseError as e:
        status, detail = 'failing', str(e)
    except Exception as e:
        log.warning('Backfill of %s failed', name, exc_info=True)
        status, detail = 'failing', f'{type(e).__name__}: {e}'

    skipped = Counter()
    if result is not None:
        skipped = Counter(result.skipped)
        seen = len(result.outings) + result.item_errors
        if result.item_errors > max(MIN_ITEM_ERRORS, MAX_ITEM_ERROR_RATIO * seen):
            status = 'failing'
            detail = f'{result.item_errors} items failed to parse out of {seen}'
        else:
            if result.item_errors or skipped['lookup_failed']:
                status = 'degraded'
                detail = (
                    f'{result.item_errors} items failed to parse, '
                    f'{skipped["lookup_failed"]} lookups failed'
                )
            try:
                summary['upserted'] = _store(
                    session, result, shift, now, settings, skipped, lookups
                )
                summary['fetched'] = len(result.outings)
            except Exception as e:
                log.warning('Backfill of %s: storing failed', name, exc_info=True)
                status, detail = 'failing', f'{type(e).__name__}: {e}'

    if status in ('ok', 'degraded'):
        state.cursor = result.cursor
        if result.cursor and result.cursor.get('done'):
            state.finished_at = now
    else:
        # nothing of the step is kept, but its outcome; the cursor stays
        session.rollback()
        state = session.scalars(
            select(BackfillPartnerState)
            .where(BackfillPartnerState.source == name)
            .with_for_update()
        ).one()
    summary['requests'] = transport.request_count
    state.floor = floor
    state.steps = (state.steps or 0) + 1
    state.requests = (state.requests or 0) + summary['requests']
    state.fetched = (state.fetched or 0) + summary['fetched']
    state.upserted = (state.upserted or 0) + summary['upserted']
    state.last_run_at = now
    state.last_status = status
    masked = {} if fixtures else secrets
    state.last_detail = _clean_detail(detail, masked) if detail else None
    session.commit()
    summary.update(
        status=status,
        detail=state.last_detail,
        cursor=state.cursor,
        skipped=dict(skipped),
    )
    log.info(
        'Backfill of %s: %s, %d upserted, %d requests, cursor %s',
        name,
        status,
        summary['upserted'],
        summary['requests'],
        state.cursor,
    )
    return summary


def reset_sources(session, names):
    """Forget where the backfill of these sources is: the next step starts over."""
    for name in names:
        row = session.get(BackfillPartnerState, name)
        if row is not None:
            session.delete(row)
    session.commit()


def states(session):
    """Return the state rows, by source."""
    return {
        row.source: row
        for row in session.scalars(
            select(BackfillPartnerState).order_by(BackfillPartnerState.source)
        )
    }


def backfill_partner_outings(
    settings, sources, floor=None, steps=1, pages=None, details=None, now=None
):
    """Run up to `steps` steps of each source; return the summaries.

    A source stops early when it is done, busy, or a step failed.
    """
    summaries = []
    for name in sources:
        for _ in range(steps):
            moment = now or datetime.datetime.now(datetime.UTC)
            with Session(
                DBSession.get_bind(), join_transaction_mode='create_savepoint'
            ) as session:
                summary = backfill_source(
                    session,
                    name,
                    settings,
                    moment,
                    floor or configured_floor(settings, moment.date()),
                    pages=pages,
                    details=details,
                )
            summaries.append(summary)
            if summary['status'] not in ('ok', 'degraded') or (
                summary.get('cursor') or {}
            ).get('done'):
                break
    return summaries


def backfill_partner_outings_job(settings):
    """Scheduler entry point: one step of each configured source. Never raises."""
    try:
        backfill_partner_outings(settings, backfill_sources(settings))
    except Exception:
        log.exception('Backfill of the partner outings failed')


def register_backfill_job(scheduler, settings):
    """Add the backfill to the scheduler when `PARTNERS_BACKFILL_SOURCES` is set."""
    try:
        sources = backfill_sources(settings)
    except ValueError:
        log.exception('PARTNERS_BACKFILL_SOURCES is wrong: no backfill')
        return
    if not sources:
        return
    every = int(_option(settings, EVERY_OPTION) or DEFAULT_EVERY_MINUTES)
    scheduler.add_job(
        backfill_partner_outings_job,
        id='backfill_partner_outings',
        name='Backfill the older partner outings (temporary)',
        trigger='interval',
        minutes=every,
        max_instances=1,
        coalesce=True,
        kwargs={'settings': settings},
    )
    log.info('Backfill of the partner outings every %d min: %s', every, sources)
