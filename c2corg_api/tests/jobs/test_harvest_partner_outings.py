"""The partner outings job, with fake adapters (no network, no real source)."""

import dataclasses
import datetime
import json
import math
from collections import Counter
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from c2corg_api import jobs
from c2corg_api.jobs import harvest_partner_outings as job
from c2corg_api.models.area import Area
from c2corg_api.models.document import DocumentGeometry
from c2corg_api.models.partner_outing import (
    PartnerLookup,
    PartnerOuting,
    PartnerSource,
)
from c2corg_api.partners.adapter import (
    ParseError,
    SourceBlocked,
    SourceDisabled,
    SourceDown,
    require_secrets,
)
from c2corg_api.partners.lookups import MemoryLookupCache
from c2corg_api.partners.model import FetchResult, HarvestedOuting, RateLimit
from c2corg_api.partners.sources import REGISTRY
from c2corg_api.partners.transport import FixtureTransport

UTC = datetime.UTC
NOW = datetime.datetime(2026, 11, 24, 12, 0, tzinfo=UTC)
TODAY = NOW.date()
SETTINGS = {
    'partners.enabled': 'true',
    'partners.sources': 'fake,other',
    'partners.interval_minutes': '15',
    'partners.retention_days': '31',
    'partners.transport': 'http',
    'partners.fixtures_dir': '',
}
EARTH = 6378137.0


def lonlat(x, y):
    """Convert web mercator coordinates to WGS 84."""
    return (
        math.degrees(x / EARTH),
        math.degrees(math.atan(math.sinh(y / EARTH))),
    )


def outing(external_id='1', source='fake', **kwargs):
    values = {
        'source': source,
        'external_id': external_id,
        'url': f'https://fake.example/{external_id}',
        'title': 'Trip',
        'date': TODAY - datetime.timedelta(days=1),
        'activities': ('skitouring',),
    }
    return HarvestedOuting(**{**values, **kwargs})


class FakeTransport:
    """A transport that is not a fixture transport: the http mode."""

    request_count = 3


def make_adapter(name='fake', fetch=None, secrets=()):
    """Build an adapter whose `fetch` is the given function."""
    calls = []

    class FakeAdapter:
        required_secrets = secrets
        site_name = f'{name}.example'
        site_url = f'https://{name}.example'
        rate = RateLimit(0, 10, 5)

        def fetch(self, ctx):
            calls.append(ctx)
            require_secrets(ctx, self.required_secrets)
            return fetch(ctx)

    FakeAdapter.name = name
    adapter = FakeAdapter()
    adapter.calls = calls
    return adapter


@pytest.fixture
def db(db_connection):
    """A session whose commits and rollbacks stay in the test's transaction."""
    with Session(db_connection, join_transaction_mode='create_savepoint') as session:
        yield session


@pytest.fixture
def fake_registry(monkeypatch):
    def register(*adapters):
        for adapter in adapters:
            monkeypatch.setitem(REGISTRY, adapter.name, type(adapter))

    return register


def run(db, adapter, now=NOW, settings=SETTINGS, transport=None, lookups=None):
    return job.run_source(
        db,
        adapter,
        transport or FakeTransport(),
        lookups or MemoryLookupCache(),
        now,
        settings,
    )


def source_row(db, name='fake'):
    db.expire_all()
    return db.get(PartnerSource, name)


def outings_of(db, source='fake'):
    db.expire_all()
    return db.scalars(
        select(PartnerOuting)
        .where(PartnerOuting.source == source)
        .order_by(PartnerOuting.external_id)
    ).all()


# ---------------------------------------------------------------- settings


def test_partners_enabled():
    assert job.partners_enabled({'partners.enabled': 'true'})
    assert job.partners_enabled({'partners.enabled': ' True '})
    assert not job.partners_enabled({'partners.enabled': 'false'})
    assert not job.partners_enabled({})


def test_enabled_sources_intersects_the_registry(fake_registry):
    fake_registry(make_adapter('fake'), make_adapter('other'))
    settings = {'partners.sources': ' fake , unknown,other,fake,'}
    assert job.enabled_sources(settings) == ['fake', 'other']
    assert job.enabled_sources({'partners.sources': ''}) == []


def test_transport_for(tmp_path):
    adapter = make_adapter()
    transport = job.transport_for(type(adapter), {'partners.transport': 'http'})
    assert type(transport).__name__ == 'HttpTransport'
    assert type(job.transport_for(type(adapter), {})).__name__ == 'HttpTransport'

    (tmp_path / 'fake').mkdir()
    (tmp_path / 'fake' / 'manifest.json').write_text(
        json.dumps({'source': 'fake', 'recorded_at': '2026-11-10', 'entries': []})
    )
    transport = job.transport_for(
        type(adapter),
        {'partners.transport': 'fixtures', 'partners.fixtures_dir': str(tmp_path)},
    )
    assert isinstance(transport, FixtureTransport)
    assert transport.rate is type(adapter).rate

    with pytest.raises(ValueError):
        job.transport_for(type(adapter), {'partners.transport': 'carrier pigeon'})


# ------------------------------------------------------------------ upsert


def test_upsert_is_idempotent_and_keeps_first_seen_at(db):
    first = datetime.datetime(2026, 11, 20, 8, 0, tzinfo=UTC)
    ids = job.upsert_outings(db, [outing(title='Old title')], first)
    db.commit()
    assert len(ids) == 1
    row = outings_of(db)[0]
    first_seen = row.first_seen_at
    assert row.fetched_at == first

    later = first + datetime.timedelta(hours=5)
    changed = outing(
        title='New title', author='Jo', orientations=('N', 'NE'), snow={'depth': 40}
    )
    assert job.upsert_outings(db, [changed], later) == ids
    db.commit()
    rows = outings_of(db)
    assert len(rows) == 1
    assert rows[0].id == ids[0]
    assert rows[0].title == 'New title'
    assert rows[0].author == 'Jo'
    assert rows[0].orientations == ['N', 'NE']
    assert rows[0].snow == {'depth': 40}
    assert rows[0].first_seen_at == first_seen
    assert rows[0].fetched_at == later


def test_upsert_columns(db):
    o = outing(
        activities=('skitouring', 'snow_ice_mixed'),
        ski_rating_min='2.1',
        ski_rating_max='3.2',
        rating_raw='3.2',
        rating_system='c2c_ski',
        steep=True,
        elevation_max=3100,
        height_diff_up=1200,
        lang='fr',
        lon=6.0,
        lat=45.0,
        geom_quality='summit',
    )
    job.upsert_outings(db, [o], NOW)
    row = outings_of(db)[0]
    assert row.activities == ['skitouring', 'snow_ice_mixed']
    assert (row.ski_rating_min, row.ski_rating_max) == ('2.1', '3.2')
    assert row.steep is True
    assert row.geom_quality == 'summit'
    x, y = db.execute(
        select(
            job.func.ST_X(PartnerOuting.geom), job.func.ST_Y(PartnerOuting.geom)
        ).where(PartnerOuting.id == row.id)
    ).one()
    assert x == pytest.approx(667916.9, abs=1)
    assert y == pytest.approx(5621521.5, abs=1)

    # an outing without coordinates has no geometry, even after an update
    job.upsert_outings(db, [dataclasses.replace(o, lon=None, lat=None)], NOW)
    row = outings_of(db)[0]
    assert (
        db.scalar(select(PartnerOuting.geom).where(PartnerOuting.id == row.id)) is None
    )


def test_upsert_batches_and_duplicates(db, monkeypatch):
    monkeypatch.setattr(job, 'BATCH_SIZE', 2)
    outings = [outing(str(i)) for i in range(5)]
    # the same item twice in one fetch: the last one wins, no error
    outings.append(outing('0', title='Last'))
    ids = job.upsert_outings(db, outings, NOW)
    assert len(ids) == 5
    rows = outings_of(db)
    assert [r.external_id for r in rows] == ['0', '1', '2', '3', '4']
    assert rows[0].title == 'Last'
    assert job.upsert_outings(db, [], NOW) == []


def test_same_external_id_in_two_sources(db):
    job.upsert_outings(db, [outing('1'), outing('1', source='other')], NOW)
    assert len(outings_of(db)) == 1
    assert len(outings_of(db, 'other')) == 1


# ------------------------------------------------------------------- areas


@pytest.fixture
def areas(db):
    """Two overlapping areas and a redirected one; points inside and outside."""

    def make(x0, y0, x1, y1, redirects_to=None):
        area = Area(area_type='range')
        area.geometry = DocumentGeometry(
            geom_detail=(
                f'SRID=3857;POLYGON(({x0} {y0},{x0} {y1},{x1} {y1},'
                f'{x1} {y0},{x0} {y0}))'
            )
        )
        area.redirects_to = redirects_to
        db.add(area)
        db.flush()
        return area

    big = make(668000, 5728000, 690000, 5746000)
    small = make(670000, 5730000, 675000, 5735000)
    redirected = make(668000, 5728000, 690000, 5746000, redirects_to=big.document_id)
    return {
        'big': big.document_id,
        'small': small.document_id,
        'redirected': redirected.document_id,
        'in_both': lonlat(672000, 5732000),
        'in_big': lonlat(685000, 5740000),
        'outside': lonlat(600000, 5600000),
    }


def test_assign_areas(db, areas):
    both = outing('both', lon=areas['in_both'][0], lat=areas['in_both'][1])
    big = outing('big', lon=areas['in_big'][0], lat=areas['in_big'][1])
    out = outing('out', lon=areas['outside'][0], lat=areas['outside'][1])
    nowhere = outing('nowhere')
    ids = job.upsert_outings(db, [both, big, out, nowhere], NOW)
    job.assign_areas(db, ids[:3])
    rows = {r.external_id: r for r in outings_of(db)}
    assert rows['both'].area_ids == sorted([areas['big'], areas['small']])
    assert rows['big'].area_ids == [areas['big']]
    assert rows['out'].area_ids == []
    assert rows['nowhere'].area_ids == []
    # the redirected area is ignored
    assert areas['redirected'] not in rows['both'].area_ids


def test_assign_areas_only_the_given_ids(db, areas):
    ids = job.upsert_outings(
        db,
        [
            outing('a', lon=areas['in_big'][0], lat=areas['in_big'][1]),
            outing('b', lon=areas['in_big'][0], lat=areas['in_big'][1]),
        ],
        NOW,
    )
    job.assign_areas(db, ids[:1])
    rows = {r.external_id: r for r in outings_of(db)}
    assert rows['a'].area_ids == [areas['big']]
    assert rows['b'].area_ids == []
    job.assign_areas(db, [])
    job.assign_areas(db)
    rows = {r.external_id: r for r in outings_of(db)}
    assert rows['b'].area_ids == [areas['big']]


def test_assign_areas_all_recomputes(db, areas):
    job.upsert_outings(
        db, [outing('a', lon=areas['in_both'][0], lat=areas['in_both'][1])], NOW
    )
    job.assign_areas(db)
    assert outings_of(db)[0].area_ids == sorted([areas['big'], areas['small']])
    # an area is edited: its polygon no longer contains the point
    small = db.get(Area, areas['small'])
    small.geometry.geom_detail = 'SRID=3857;POLYGON((0 0,0 1,1 1,1 0,0 0))'
    db.flush()
    job.assign_areas(db)
    assert outings_of(db)[0].area_ids == [areas['big']]


def test_reupsert_resets_the_areas_of_a_moved_outing(db, areas):
    o = outing('a', lon=areas['in_both'][0], lat=areas['in_both'][1])
    ids = job.upsert_outings(db, [o], NOW)
    job.assign_areas(db, ids)
    moved = dataclasses.replace(o, lon=areas['outside'][0], lat=areas['outside'][1])
    ids = job.upsert_outings(db, [moved], NOW)
    job.assign_areas(db, ids)
    assert outings_of(db)[0].area_ids == []


# ------------------------------------------------------------------- purge


def test_purge(db, areas):
    old = TODAY - datetime.timedelta(days=32)
    limit = TODAY - datetime.timedelta(days=31)
    lon, lat = areas['in_big']
    job.upsert_outings(
        db,
        [
            outing('old', date=old),
            outing('limit', date=limit, lon=lon, lat=lat),
            outing('new', lon=lon, lat=lat),
        ],
        NOW,
    )
    assert job.purge_partner_outings(db, NOW, 31) == 1
    rows = {r.external_id: r for r in outings_of(db)}
    assert sorted(rows) == ['limit', 'new']
    # the areas of the remaining rows are recomputed
    assert rows['new'].area_ids == [areas['big']]
    assert job.purge_partner_outings(db, NOW, 31) == 0
    assert job.purge_partner_outings(db, NOW, 0) == 2


def test_purge_job(db, db_connection):
    job.upsert_outings(
        db, [outing('old', date=TODAY - datetime.timedelta(days=40))], NOW
    )
    db.commit()
    job.purge_partner_outings_job(SETTINGS)
    assert outings_of(db) == []


# ------------------------------------------------------------------ lookups


def test_db_lookup_cache(db):
    cache = job.DbLookupCache(db, 'fake')
    other = job.DbLookupCache(db, 'other')
    assert cache.get('route:1') is None
    cache.put('route:1', {'name': 'Col', 'alt': [1, 2]})
    assert cache.get('route:1') == {'name': 'Col', 'alt': [1, 2]}
    # an update replaces the data
    cache.put('route:1', {'name': 'Col du Lac'})
    assert cache.get('route:1') == {'name': 'Col du Lac'}
    assert db.scalar(select(job.func.count()).select_from(PartnerLookup)) == 1
    # per source
    assert other.get('route:1') is None


# ----------------------------------------------------------- health, status


def ok_fetch(ctx):
    return FetchResult([outing('1'), outing('2')], cursor={'page': 2})


def test_status_ok(db):
    adapter = make_adapter(fetch=ok_fetch)
    assert run(db, adapter) == 'ok'
    row = source_row(db)
    assert row.status == 'ok'
    assert row.status_detail is None
    assert row.last_run_at == NOW
    assert row.last_success_at == NOW
    assert row.last_error_at is None
    assert row.consecutive_failures == 0
    assert row.last_fetched == 2
    assert row.last_upserted == 2
    assert row.last_requests == 3
    assert row.last_duration_ms >= 0
    assert row.last_skipped == {}
    assert row.cursor == {'page': 2}
    assert [o.external_id for o in outings_of(db)] == ['1', '2']


def raises(exception):
    def fetch(ctx):
        raise exception

    return fetch


@pytest.mark.parametrize(
    'exception, status, counts_as_failure',
    [
        (SourceDown('HTTP 503'), 'down', True),
        (SourceBlocked('HTTP 403 Cloudflare challenge'), 'blocked', True),
        (ParseError('unexpected shape'), 'failing', True),
        (KeyError('title'), 'failing', True),
        (SourceDisabled('KEY not set'), 'disabled', False),
    ],
)
def test_status_of_exceptions(db, exception, status, counts_as_failure):
    adapter = make_adapter(fetch=raises(exception))
    assert run(db, adapter) == status
    row = source_row(db)
    assert row.status == status
    assert row.status_detail
    assert row.last_run_at == NOW
    assert row.last_success_at is None
    assert row.consecutive_failures == (1 if counts_as_failure else 0)
    assert (row.last_error_at == NOW) == counts_as_failure
    assert outings_of(db) == []


def test_disabled_by_missing_secret(db, monkeypatch):
    monkeypatch.delenv('FAKE_KEY', raising=False)
    adapter = make_adapter(fetch=ok_fetch, secrets=('FAKE_KEY',))
    assert run(db, adapter) == 'disabled'
    assert source_row(db).status_detail == 'FAKE_KEY not set'
    assert outings_of(db) == []

    # the secret comes from the environment
    monkeypatch.setenv('FAKE_KEY', 's3cr3t-value')
    assert run(db, adapter) == 'ok'
    assert adapter.calls[-1].secrets == {'FAKE_KEY': 's3cr3t-value'}


def test_no_secret_in_the_detail(db, monkeypatch):
    monkeypatch.setenv('FAKE_KEY', 's3cr3t-value')
    adapter = make_adapter(
        fetch=raises(SourceBlocked('401 for https://x/?key=s3cr3t-value')),
        secrets=('FAKE_KEY',),
    )
    assert run(db, adapter) == 'blocked'
    detail = source_row(db).status_detail
    assert 's3cr3t-value' not in detail
    assert '***' in detail


def test_no_url_encoded_secret_in_the_detail(db, monkeypatch):
    monkeypatch.setenv('FAKE_KEY', 'a/b c+d')
    adapter = make_adapter(
        fetch=raises(SourceDown('503 for https://x/?key=a%2Fb+c%2Bd&k=a%2Fb%20c%2Bd')),
        secrets=('FAKE_KEY',),
    )
    run(db, adapter)
    assert source_row(db).status_detail == '503 for https://x/?key=***&k=***'


def test_detail_is_truncated(db):
    adapter = make_adapter(fetch=raises(SourceDown('x' * 2000)))
    run(db, adapter)
    assert len(source_row(db).status_detail) == 500


def test_item_errors_under_budget_degrade(db):
    def fetch(ctx):
        # 3 errors: not more than max(3, 10%)
        return FetchResult([outing('1')], item_errors=3, cursor={'c': 1})

    assert run(db, make_adapter(fetch=fetch)) == 'degraded'
    row = source_row(db)
    assert row.status == 'degraded'
    assert '3' in row.status_detail
    assert row.last_success_at == NOW
    assert row.consecutive_failures == 0
    assert row.cursor == {'c': 1}
    assert len(outings_of(db)) == 1


def test_item_errors_ratio_budget(db):
    # 10 errors for 100 items + 10: 10 <= 11
    def fetch(ctx):
        return FetchResult([outing(str(i)) for i in range(100)], item_errors=10)

    assert run(db, make_adapter(fetch=fetch)) == 'degraded'
    assert len(outings_of(db)) == 100


def test_item_errors_over_budget_fail_and_upsert_nothing(db):
    def fetch(ctx):
        return FetchResult([outing('1')], item_errors=4, cursor={'c': 9})

    assert run(db, make_adapter(fetch=fetch)) == 'failing'
    row = source_row(db)
    assert row.status == 'failing'
    assert row.last_success_at is None
    assert row.consecutive_failures == 1
    assert row.last_upserted == 0
    assert row.cursor is None
    assert outings_of(db) == []


def test_item_errors_over_the_ratio_fail(db):
    def fetch(ctx):
        return FetchResult([outing(str(i)) for i in range(20)], item_errors=4)

    # 4 > max(3, 2.4)
    assert run(db, make_adapter(fetch=fetch)) == 'failing'
    assert outings_of(db) == []


def test_recovery_resets_failures(db):
    down = make_adapter(fetch=raises(SourceDown('503')))
    run(db, down)
    run(db, down, now=NOW + datetime.timedelta(hours=1))
    assert source_row(db).consecutive_failures == 2
    assert run(db, make_adapter(fetch=ok_fetch), now=NOW + datetime.timedelta(hours=2))
    row = source_row(db)
    assert row.status == 'ok'
    assert row.consecutive_failures == 0
    assert row.last_error_at == NOW + datetime.timedelta(hours=1)
    assert row.status_detail is None


def test_skipped_counters_and_too_old(db):
    old = TODAY - datetime.timedelta(days=40)

    def fetch(ctx):
        return FetchResult(
            [outing('1'), outing('old', date=old)],
            skipped=Counter({'unmapped_activity:climb': 4, 'parse_error': 1}),
        )

    assert run(db, make_adapter(fetch=fetch)) == 'ok'
    row = source_row(db)
    assert row.last_skipped == {
        'unmapped_activity:climb': 4,
        'parse_error': 1,
        'too_old': 1,
    }
    assert row.last_fetched == 2
    assert row.last_upserted == 1
    assert [o.external_id for o in outings_of(db)] == ['1']


def test_areas_are_assigned_by_the_run(db, areas):
    lon, lat = areas['in_both']

    def fetch(ctx):
        return FetchResult([outing('1', lon=lon, lat=lat), outing('2')])

    run(db, make_adapter(fetch=fetch))
    rows = {o.external_id: o for o in outings_of(db)}
    assert rows['1'].area_ids == sorted([areas['big'], areas['small']])
    assert rows['2'].area_ids == []


def test_second_fetch_of_the_same_item_updates_it(db):
    versions = iter(['First', 'Second'])

    def fetch(ctx):
        return FetchResult([outing('1', title=next(versions))])

    adapter = make_adapter(fetch=fetch)
    run(db, adapter)
    first_seen = outings_of(db)[0].first_seen_at
    run(db, adapter, now=NOW + datetime.timedelta(minutes=15))
    rows = outings_of(db)
    assert len(rows) == 1
    assert rows[0].title == 'Second'
    assert rows[0].first_seen_at == first_seen
    assert rows[0].fetched_at == NOW + datetime.timedelta(minutes=15)


def test_storing_error_fails_the_source_not_the_job(db):
    # a title too long for the column: the database refuses the batch
    def fetch(ctx):
        return FetchResult([outing('1', title='x' * 400)], cursor={'c': 1})

    assert run(db, make_adapter(fetch=fetch)) == 'failing'
    row = source_row(db)
    assert row.status == 'failing'
    assert row.cursor is None
    assert outings_of(db) == []


# ------------------------------------------------------------------ backoff


def test_backoff(db):
    adapter = make_adapter(fetch=raises(SourceDown('503')))
    for i in range(4):
        # spaced by more than any backoff window
        run(db, adapter, now=NOW + datetime.timedelta(days=i))
    row = source_row(db)
    assert row.consecutive_failures == 4
    assert len(adapter.calls) == 4
    last = NOW + datetime.timedelta(days=3)

    # 4 failures: waits interval * 2**2 = 60 minutes
    assert run(db, adapter, now=last + datetime.timedelta(minutes=59)) == 'down'
    assert len(adapter.calls) == 4
    row = source_row(db)
    assert row.last_run_at == last
    assert row.consecutive_failures == 4

    # the next tick, read a few ms early, is not skipped
    tick = last + datetime.timedelta(minutes=60, milliseconds=-5)
    assert run(db, adapter, now=tick) == 'down'
    assert len(adapter.calls) == 5
    assert source_row(db).consecutive_failures == 5


def test_no_backoff_before_three_failures(db):
    adapter = make_adapter(fetch=raises(SourceDown('503')))
    for i in range(3):
        run(db, adapter, now=NOW + datetime.timedelta(minutes=i))
    assert len(adapter.calls) == 3
    # 3 failures: waits 15 * 2 = 30 minutes
    run(db, adapter, now=NOW + datetime.timedelta(minutes=10))
    assert len(adapter.calls) == 3
    run(db, adapter, now=NOW + datetime.timedelta(minutes=32))
    assert len(adapter.calls) == 4


def test_backoff_is_capped(db):
    row = job._get_source_row(db, 'fake')
    row.consecutive_failures = 50
    row.last_run_at = NOW
    # 15 * 2**4 = 240 minutes at most
    adapter = make_adapter(fetch=ok_fetch)
    assert run(db, adapter, now=NOW + datetime.timedelta(minutes=239)) == 'never_run'
    assert adapter.calls == []
    assert run(db, adapter, now=NOW + datetime.timedelta(minutes=240)) == 'ok'


# -------------------------------------------------------------------- since


def test_since_first_run_and_clamp(db):
    adapter = make_adapter(fetch=ok_fetch)
    run(db, adapter)
    # never run: 14 days back, minus the 2 days of overlap
    assert adapter.calls[0].since == TODAY - datetime.timedelta(days=16)
    assert adapter.calls[0].cursor is None
    assert adapter.calls[0].now == NOW

    # last success 3 hours ago: overlap of 2 days
    later = NOW + datetime.timedelta(hours=3)
    run(db, adapter, now=later)
    assert adapter.calls[1].since == TODAY - datetime.timedelta(days=2)
    assert adapter.calls[1].cursor == {'page': 2}

    # a long outage: clamped to the retention
    much_later = NOW + datetime.timedelta(days=60)
    run(db, adapter, now=much_later)
    assert adapter.calls[2].since == much_later.date() - datetime.timedelta(days=31)


def test_since_uses_the_last_success_not_the_last_run(db):
    adapter = make_adapter(fetch=ok_fetch)
    run(db, adapter)
    fail = make_adapter(fetch=raises(SourceDown('503')))
    run(db, fail, now=NOW + datetime.timedelta(days=5))
    run(db, adapter, now=NOW + datetime.timedelta(days=6))
    # the success of day 0, not the failure of day 5
    assert adapter.calls[1].since == TODAY - datetime.timedelta(days=2)


# ------------------------------------------------------------------ cursors


def test_cursor_rules(db):
    results = iter(
        [
            FetchResult([outing('1')], cursor={'n': 1}),
            # returning the previous cursor keeps it
            None,
            # None clears it
            FetchResult([outing('3')], cursor=None),
        ]
    )
    seen = []

    def fetch(ctx):
        seen.append(ctx.cursor)
        result = next(results)
        if result is None:
            return FetchResult([outing('2')], cursor=dict(ctx.cursor))
        return result

    adapter = make_adapter(fetch=fetch)
    step = datetime.timedelta(minutes=15)
    run(db, adapter, now=NOW)
    assert source_row(db).cursor == {'n': 1}
    run(db, adapter, now=NOW + step)
    assert source_row(db).cursor == {'n': 1}
    run(db, adapter, now=NOW + 2 * step)
    assert source_row(db).cursor is None
    assert seen == [None, {'n': 1}, {'n': 1}]


def test_a_failed_run_keeps_the_cursor(db):
    run(db, make_adapter(fetch=ok_fetch))
    assert source_row(db).cursor == {'page': 2}
    step = datetime.timedelta(minutes=15)
    run(db, make_adapter(fetch=raises(SourceDown('503'))), now=NOW + step)
    assert source_row(db).cursor == {'page': 2}

    def too_many_errors(ctx):
        return FetchResult([], item_errors=10, cursor={'page': 99})

    run(db, make_adapter(fetch=too_many_errors), now=NOW + 2 * step)
    row = source_row(db)
    assert row.status == 'failing'
    assert row.cursor == {'page': 2}


# ------------------------------------------------------------- fixture mode


@pytest.fixture
def fixtures_dir(tmp_path):
    directory = tmp_path / 'fake'
    directory.mkdir()
    (directory / 'manifest.json').write_text(
        json.dumps(
            {
                'source': 'fake',
                'recorded_at': '2026-11-10',
                'synthetic': True,
                'entries': [],
            }
        )
    )
    return tmp_path


def fixture_transport(fixtures_dir, adapter):
    return FixtureTransport(fixtures_dir, 'fake', rate=type(adapter).rate)


def test_fixture_mode_shifts_the_dates(db, fixtures_dir, caplog):
    def fetch(ctx):
        # the recording day, 3 days before it, and a day that is too old once
        # shifted (51 days before the recording: 65 days before today)
        return FetchResult(
            [
                outing('rec', date=datetime.date(2026, 11, 10)),
                outing('three', date=datetime.date(2026, 11, 7)),
                outing('old', date=datetime.date(2026, 9, 20)),
            ]
        )

    adapter = make_adapter(fetch=fetch, secrets=('FAKE_KEY', 'OTHER'))
    with caplog.at_level('WARNING'):
        status = run(db, adapter, transport=fixture_transport(fixtures_dir, adapter))
    assert status == 'ok'
    rows = {o.external_id: o for o in outings_of(db)}
    # 14 days of shift: today - recorded_at
    assert rows['rec'].date == TODAY
    assert rows['three'].date == TODAY - datetime.timedelta(days=3)
    assert 'old' not in rows
    assert source_row(db).last_skipped == {'too_old': 1}
    assert len([r for r in caplog.records if 'shifted' in r.getMessage()]) == 1
    # no secret needed in fixture mode
    assert adapter.calls[0].secrets == {'FAKE_KEY': 'fixture', 'OTHER': 'fixture'}


def test_fixture_mode_shift_follows_the_clock(db, fixtures_dir):
    adapter = make_adapter(
        fetch=lambda ctx: FetchResult([outing('rec', date=datetime.date(2026, 11, 10))])
    )
    transport = fixture_transport(fixtures_dir, adapter)
    run(db, adapter, now=NOW + datetime.timedelta(days=2), transport=transport)
    assert outings_of(db)[0].date == TODAY + datetime.timedelta(days=2)


def test_fixture_mode_gives_the_adapter_the_recording_clock(db, fixtures_dir):
    # weeks after the recording, the adapter still sees the recorded items as
    # recent: its `since` filter must not drop them
    later = NOW + datetime.timedelta(days=40)
    adapter = make_adapter(
        fetch=lambda ctx: FetchResult([outing('rec', date=datetime.date(2026, 11, 9))])
    )
    transport = fixture_transport(fixtures_dir, adapter)
    run(db, adapter, now=later, transport=transport)
    ctx = adapter.calls[0]
    # recorded on 2026-11-10: the first run reads 16 days before it
    assert ctx.now == datetime.datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
    assert ctx.since == datetime.date(2026, 10, 25)
    assert outings_of(db)[0].date == later.date() - datetime.timedelta(days=1)


def test_http_mode_never_shifts_the_dates(db):
    date = TODAY - datetime.timedelta(days=3)
    adapter = make_adapter(fetch=lambda ctx: FetchResult([outing('1', date=date)]))
    run(db, adapter)
    assert outings_of(db)[0].date == date


def test_fixture_mode_end_to_end(db, db_connection, fixtures_dir, fake_registry):
    adapter = make_adapter(
        fetch=lambda ctx: FetchResult(
            [outing('rec', date=datetime.date(2026, 11, 10))], cursor={'a': 1}
        )
    )
    fake_registry(adapter)
    settings = {
        **SETTINGS,
        'partners.sources': 'fake',
        'partners.transport': 'fixtures',
        'partners.fixtures_dir': str(fixtures_dir),
    }
    job.harvest_partner_outings(settings, now=NOW)
    assert outings_of(db)[0].date == TODAY
    assert source_row(db).status == 'ok'


# ------------------------------------------------------------ the whole job


def test_one_failing_source_does_not_stop_the_others(
    db, db_connection, fake_registry, monkeypatch
):
    monkeypatch.delenv('FAKE_KEY', raising=False)
    boom = make_adapter('boom', fetch=raises(SourceDown('503')))
    blocked = make_adapter('blocked', fetch=raises(SourceBlocked('403')))
    crash = make_adapter('crash', fetch=raises(RuntimeError('bug')))
    disabled = make_adapter('disabled', fetch=ok_fetch, secrets=('FAKE_KEY',))
    good = make_adapter(
        'good', fetch=lambda ctx: FetchResult([outing('7', source='good')])
    )
    fake_registry(boom, blocked, crash, disabled, good)
    settings = {**SETTINGS, 'partners.sources': 'boom,blocked,crash,disabled,good'}

    job.harvest_partner_outings(settings, now=NOW)

    statuses = {
        name: source_row(db, name).status
        for name in ('boom', 'blocked', 'crash', 'disabled', 'good')
    }
    assert statuses == {
        'boom': 'down',
        'blocked': 'blocked',
        'crash': 'failing',
        'disabled': 'disabled',
        'good': 'ok',
    }
    assert [o.external_id for o in outings_of(db, 'good')] == ['7']
    # nothing was lost: the next run goes on
    job.harvest_partner_outings(settings, now=NOW + datetime.timedelta(hours=1))
    assert source_row(db, 'good').last_run_at == NOW + datetime.timedelta(hours=1)


def test_harvest_records_a_source_that_cannot_start(
    db, db_connection, fake_registry, fixtures_dir, tmp_path
):
    # fixtures requested but the manifest of the source is missing
    fake_registry(make_adapter('nofixture', fetch=ok_fetch))
    settings = {
        **SETTINGS,
        'partners.sources': 'nofixture',
        'partners.transport': 'fixtures',
        'partners.fixtures_dir': str(tmp_path),
    }
    job.harvest_partner_outings(settings, now=NOW)
    row = source_row(db, 'nofixture')
    assert row.status == 'failing'
    assert 'manifest.json' in row.status_detail
    assert row.consecutive_failures == 1


def test_harvest_uses_the_lookup_cache(db, db_connection, fake_registry):
    def fetch(ctx):
        if ctx.lookups.get('route:1') is None:
            ctx.lookups.put('route:1', {'name': 'Col'})
        return FetchResult([outing('1', source='fake')])

    fake_registry(make_adapter('fake', fetch=fetch))
    job.harvest_partner_outings({**SETTINGS, 'partners.sources': 'fake'}, now=NOW)
    db.expire_all()
    assert db.get(PartnerLookup, ('fake', 'route:1')).data == {'name': 'Col'}


def test_lookups_survive_a_down_source(db):
    def fetch(ctx):
        ctx.lookups.put('route:1', {'name': 'Col'})
        raise SourceDown('503')

    run(db, make_adapter(fetch=fetch), lookups=job.DbLookupCache(db, 'fake'))
    assert db.get(PartnerLookup, ('fake', 'route:1')).data == {'name': 'Col'}


# ---------------------------------------------------------------- scheduler


def scheduled_jobs(settings):
    with (
        patch.object(jobs, 'BackgroundScheduler') as scheduler_class,
        patch.object(jobs.atexit, 'register'),
    ):
        jobs.configure_scheduler_from_config(settings)
    return {
        call.kwargs['id']: call.kwargs
        for call in scheduler_class.return_value.add_job.call_args_list
    }


def test_scheduler_adds_the_jobs_only_when_enabled():
    added = scheduled_jobs({'partners.enabled': 'false'})
    assert 'harvest_partner_outings' not in added
    assert 'purge_partner_outings' not in added
    assert 'purge_token' in added


def test_scheduler_adds_the_partner_jobs():
    settings = {'partners.enabled': 'true', 'partners.interval_minutes': '20'}
    added = scheduled_jobs(settings)
    harvest = added['harvest_partner_outings']
    assert harvest['trigger'] == 'interval'
    assert harvest['minutes'] == 20
    assert harvest['max_instances'] == 1
    assert harvest['coalesce'] is True
    assert harvest['kwargs'] == {'settings': settings}
    delay = harvest['next_run_time'] - datetime.datetime.now(UTC)
    assert datetime.timedelta(seconds=20) < delay <= datetime.timedelta(seconds=30)
    purge = added['purge_partner_outings']
    assert (purge['trigger'], purge['hour'], purge['minute']) == ('cron', 1, 40)
    assert purge['kwargs'] == {'settings': settings}


def test_harvest_script_runs_the_job_once():
    from c2corg_api.scripts.jobs import harvest_partners

    with (
        patch.object(harvest_partners, 'setup_logging'),
        patch.object(harvest_partners, 'get_appsettings', return_value={'a': 1}),
        patch.object(harvest_partners, 'engine_from_config'),
        patch.object(harvest_partners.DBSession, 'configure'),
        patch.object(harvest_partners, 'harvest_partner_outings') as harvest,
    ):
        harvest_partners.main(['x', 'development.ini'])
    harvest.assert_called_once_with({'a': 1})
    with pytest.raises(SystemExit):
        harvest_partners.main(['x'])
