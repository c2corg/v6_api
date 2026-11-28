"""TEMPORARY: the backfillers of the partner sources, on fixtures (no network).

Delete with the other `backfill_*` files (c2corg/v6_api#2763).
"""

import datetime
from pathlib import Path

import pytest

from c2corg_api.partners import backfill_sources as bf
from c2corg_api.partners.adapter import ParseError, SourceDisabled, SourceDown
from c2corg_api.partners.backfill_transport import (
    BackfillFixtureTransport,
    BackfillHttpTransport,
)
from c2corg_api.partners.lookups import MemoryLookupCache
from c2corg_api.partners.model import FetchContext, RateLimit
from c2corg_api.partners.sources import REGISTRY
from c2corg_api.partners.transport import HttpResponse

FIXTURES = Path(__file__).parent / 'backfill_fixtures'


def run(name, floor, pages=None, details=None, cursor=None, lookups=None):
    """Run a step on the fixtures, on the day of their recording."""
    backfiller = bf.BACKFILLERS[name]()
    pages = pages or backfiller.pages_per_run
    details = backfiller.details_per_run if details is None else details
    transport = BackfillFixtureTransport(
        FIXTURES, name, rate=RateLimit(0, backfiller.requests(pages, details), 1)
    )
    recorded = datetime.date.fromisoformat(transport.recorded_at)
    ctx = FetchContext(
        since=floor,
        now=datetime.datetime.combine(recorded, datetime.time(12), datetime.UTC),
        cursor=cursor,
        transport=transport,
        lookups=lookups if lookups is not None else MemoryLookupCache(),
        secrets={name: 'fixture' for name in REGISTRY[name].required_secrets},
    )
    return backfiller.step(ctx, pages, details), transport


def test_one_backfiller_per_source():
    assert set(bf.BACKFILLERS) == set(REGISTRY)
    for name, cls in bf.BACKFILLERS.items():
        assert cls.name == name
        assert cls().requests(cls.pages_per_run, cls.details_per_run) > 0


@pytest.mark.parametrize(
    'day,season',
    [
        (datetime.date(2026, 8, 31), 2026),
        (datetime.date(2026, 9, 1), 2027),
        (datetime.date(2026, 11, 28), 2027),
    ],
)
def test_season_of(day, season):
    assert bf.season_of(day) == season


# -- skitour.fr --------------------------------------------------------------


def test_skitour_walks_the_seasons_down_to_the_floor():
    result, transport = run('skitour', datetime.date(2025, 1, 1))
    # seasons 2027 (the recording), 2026 (two outings), 2025 (empty); 2024
    # ends before the floor
    assert transport.request_count == 3
    assert result.cursor == {'season': 2024, 'page': 1, 'done': True}
    ids = {o.external_id for o in result.outings}
    assert {'900001', '900002'} <= ids
    assert len(ids) == 32
    old = next(o for o in result.outings if o.external_id == '900001')
    assert old.date == datetime.date(2026, 2, 15)
    assert old.source == 'skitour'
    assert old.url == 'https://skitour.fr/sorties/900001'


def test_skitour_resumes_and_keeps_to_its_pages():
    first, transport = run('skitour', datetime.date(2025, 1, 1), pages=1)
    assert transport.request_count == 1
    assert first.cursor == {'season': 2026, 'page': 1}
    second, _ = run('skitour', datetime.date(2025, 1, 1), pages=1, cursor=first.cursor)
    assert {o.external_id for o in second.outings} == {'900001', '900002'}
    assert second.cursor == {'season': 2025, 'page': 1}


def test_skitour_pages_a_full_season(monkeypatch):
    monkeypatch.setattr(bf.SkitourBackfill, 'PAGE_SIZE', 2)
    calls = []

    class Transport:
        request_count = 0

        def get(self, url, *, params=None, headers=None):
            calls.append(dict(params))
            # a full page (2 outings), then the rest of the season (none)
            if params['p'] == 1:
                body = (
                    b'[{"id": "1", "titre": "a", "date": "1770000000"},'
                    b' {"id": "2", "titre": "b", "date": "1770000000"}]'
                )
            else:
                body = b'[]'
            return HttpResponse(200, {}, body, url)

    ctx = FetchContext(
        since=datetime.date(2026, 1, 1),
        now=datetime.datetime(2026, 3, 1, tzinfo=datetime.UTC),
        cursor=None,
        transport=Transport(),
        lookups=MemoryLookupCache(),
        secrets={'SKITOUR_API_KEY': 'k'},
    )
    result = bf.SkitourBackfill().step(ctx, 5, 0)
    assert [(c['a'], c['p']) for c in calls] == [(2026, 1), (2026, 2)]
    assert result.cursor == {'season': 2025, 'page': 1, 'done': True}
    assert all(c['l'] == 2 and c['c'] == 1 for c in calls)


def test_skitour_needs_its_key():
    ctx = FetchContext(
        since=datetime.date(2025, 1, 1),
        now=datetime.datetime(2026, 3, 1, tzinfo=datetime.UTC),
        cursor=None,
        transport=None,
        lookups=MemoryLookupCache(),
        secrets={},
    )
    with pytest.raises(SourceDisabled):
        bf.SkitourBackfill().step(ctx, 1, 0)


# -- gulliver.it -------------------------------------------------------------


def test_gulliver_pages_to_the_end_and_reads_routes():
    lookups = MemoryLookupCache()
    result, transport = run(
        'gulliver', datetime.date(2020, 1, 1), pages=5, details=2, lookups=lookups
    )
    # pages 1, 2, the empty page 3, two routes; no front page
    assert transport.request_count == 5
    assert result.cursor == {'page': 3, 'done': True}
    assert result.item_errors == 0
    assert len(result.outings) == 59
    located = [o for o in result.outings if o.lat is not None]
    assert len(located) == 2 and {o.geom_quality for o in located} == {'start'}
    assert result.skipped['route_lookup_deferred'] == 57
    # the reports and routes read are cached for the harvest
    assert lookups.get('route:10191') is not None
    assert lookups.get(f'report:{result.outings[0].external_id}') is not None


def test_gulliver_stops_at_the_floor():
    result, transport = run('gulliver', datetime.date(2026, 11, 27), details=0)
    assert result.cursor['done'] is True
    # page 1 reaches the floor, page 2 is wholly older: the walk ends there
    assert transport.request_count == 2
    assert result.skipped['too_old'] > 0
    assert all(o.date >= datetime.date(2026, 11, 27) for o in result.outings)


# -- bivouak.net -------------------------------------------------------------


def test_bivouak_walks_each_sport():
    result, transport = run('bivouak', datetime.date(2026, 9, 1), pages=12, details=2)
    assert transport.request_count == 12  # 10 pages of lists, 2 detail pages
    assert result.cursor == {'sport': 5, 'start': 1, 'done': True}
    assert result.item_errors == 0
    assert all(o.date >= datetime.date(2026, 9, 1) for o in result.outings)
    assert result.skipped['too_old'] > 0
    assert result.skipped['location_deferred'] == len(result.outings) - 2
    sports = {o.source_activity for o in result.outings}
    assert {'ski', 'rando', 'parapente'} <= sports


def test_bivouak_resumes_from_its_cursor():
    first, _ = run('bivouak', datetime.date(2026, 9, 1), pages=2, details=0)
    assert first.cursor == {'sport': 1, 'start': 1}
    second, _ = run(
        'bivouak', datetime.date(2026, 9, 1), pages=2, details=0, cursor=first.cursor
    )
    assert {o.source_activity for o in second.outings} == {'rando'}
    assert second.cursor == {'sport': 2, 'start': 1}


def test_bivouak_page_past_the_end():
    class Transport:
        request_count = 0

        def get(self, url, *, params=None, headers=None):
            body = '<html><body><p>Aucune sortie ici pour le moment</p></body></html>'
            return HttpResponse(200, {}, body.encode(), url)

    ctx = FetchContext(
        since=datetime.date(2000, 1, 1),
        now=datetime.datetime(2026, 11, 28, tzinfo=datetime.UTC),
        cursor={'sport': 4, 'start': 300},
        transport=Transport(),
        lookups=MemoryLookupCache(),
        secrets={},
    )
    result = bf.BivouakBackfill().step(ctx, 3, 0)
    assert result.cursor == {'sport': 5, 'start': 1, 'done': True}


def test_bivouak_page_without_a_list_fails():
    class Transport:
        request_count = 0

        def get(self, url, *, params=None, headers=None):
            return HttpResponse(200, {}, b'<html><body>?</body></html>', url)

    ctx = FetchContext(
        since=datetime.date(2000, 1, 1),
        now=datetime.datetime(2026, 11, 28, tzinfo=datetime.UTC),
        cursor=None,
        transport=Transport(),
        lookups=MemoryLookupCache(),
        secrets={},
    )
    with pytest.raises(ParseError):
        bf.BivouakBackfill().step(ctx, 1, 0)


# -- gipfelbuch.ch -----------------------------------------------------------


def test_gipfelbuch_posts_the_form_down_to_the_floor():
    result, transport = run(
        'gipfelbuch', datetime.date(2026, 11, 22), pages=5, details=2
    )
    # the listing (token), offsets 0, 66, 132, two summit pages
    assert transport.request_count == 6
    assert result.cursor == {'offset': 198, 'done': True}
    assert result.item_errors == 0
    assert len(result.outings) == 6
    assert sum(o.geom_quality == 'summit' for o in result.outings) == 2
    first = result.outings[0]
    assert first.url == f'https://www.gipfelbuch.ch/verhaeltnisse/{first.external_id}'
    assert first.lang == 'de' and first.elevation_max and first.summit_name
    assert first.author.startswith('user')


def test_gipfelbuch_rows_read_as_the_listing():
    """A rendered row gives the outing the listing page would give."""
    template = (
        '<article class="item list-item{{#isinactive}} inactive{{/isinactive}}" '
        'id="conditions{{id}}"><span class="column main-icon"><i data-tooltip='
        '"{{type}}"></i></span><span class="main-title"><div class="main" '
        'data-tooltip="{{mainpoint}}">{{mainpoint}}</div></span><span class='
        '"regions"><div>{{region}}</div><div>{{region_group}}</div></span><span '
        'class="information"><span class="date" data-tooltip="{{#isnew}}Neuer '
        'Eintrag<br>{{/isnew}}Datum Tour: {{datum}}">{{datum}}</span>'
        '{{#hasautorinfos}}<div class="autor-infos"><span>{{autor}}</span></div>'
        '{{/hasautorinfos}}</span></article>'
    )
    markup = bf.render_template(
        template,
        {
            'id': 7,
            'type': 'Skitour',
            'mainpoint': 'Piz "Test" (3001m)',
            'region': 'CH - Graubünden',
            'region_group': 'Schweiz',
            'datum': '06.03.2026',
            'isnew': True,
            'isinactive': False,
            'hasautorinfos': True,
            'autor': 'a &amp; b',
        },
    )
    assert 'inactive' not in markup
    assert 'Neuer Eintrag' in markup
    assert 'data-tooltip="Piz &quot;Test&quot; (3001m)"' in markup
    assert '{{' not in markup


def test_gipfelbuch_end_of_the_list():
    class Transport:
        request_count = 0

        def get(self, url, *, params=None, headers=None):
            body = b'<input id="dvf_csrf_token" name="dvf_csrf_token" value="t">'
            return HttpResponse(200, {}, body, url)

        def post(self, url, *, data, headers=None):
            assert data['dvf_csrf_token'] == 't'
            assert data['filter_conditions_offset'] == '990'
            body = (
                b'{"items": [{"message": "Es wurden keine Eintr\\u00e4ge gefunden"}],'
                b' "meta": {"total": 3}, "template": "<div>{{message}}</div>"}'
            )
            return HttpResponse(200, {}, body, url)

    ctx = FetchContext(
        since=datetime.date(2000, 1, 1),
        now=datetime.datetime(2026, 11, 28, tzinfo=datetime.UTC),
        cursor={'offset': 990},
        transport=Transport(),
        lookups=MemoryLookupCache(),
        secrets={},
    )
    result = bf.GipfelbuchBackfill().step(ctx, 3, 0)
    assert result.cursor == {'offset': 990, 'done': True}
    assert result.outings == []


def test_gipfelbuch_without_token_fails():
    class Transport:
        request_count = 0

        def get(self, url, *, params=None, headers=None):
            return HttpResponse(200, {}, b'<html></html>', url)

    ctx = FetchContext(
        since=datetime.date(2000, 1, 1),
        now=datetime.datetime(2026, 11, 28, tzinfo=datetime.UTC),
        cursor=None,
        transport=Transport(),
        lookups=MemoryLookupCache(),
        secrets={},
    )
    with pytest.raises(ParseError, match='token'):
        bf.GipfelbuchBackfill().step(ctx, 1, 0)


# -- skitourenportal.eu ------------------------------------------------------


def test_skitourenportal_walks_each_state():
    result, transport = run('skitourenportal', datetime.date(2026, 10, 1), pages=12)
    assert transport.request_count == 8
    assert result.cursor == {'state': 5, 'page': 1, 'done': True}
    assert result.item_errors == 0
    assert result.outings and all(
        o.activities == ('skitouring',) and o.country == 'AT' for o in result.outings
    )
    assert {o.region for o in result.outings} >= {'Salzburg'}
    assert any(o.geom_quality == 'route' for o in result.outings)


def test_skitourenportal_resumes_within_a_state():
    first, transport = run('skitourenportal', datetime.date(2026, 10, 1), pages=1)
    assert transport.request_count == 1
    assert first.cursor == {'state': 0, 'page': 2}
    second, _ = run(
        'skitourenportal', datetime.date(2026, 10, 1), pages=1, cursor=first.cursor
    )
    assert second.cursor == {'state': 1, 'page': 1}


# -- on-ice.it ---------------------------------------------------------------


def test_onice_walks_the_list_of_each_type():
    result, transport = run('onice', datetime.date(2026, 10, 1), pages=5, details=2)
    # the first page of the 5 types (3 rows each: each list ends), 2 details
    assert transport.request_count == 7
    assert result.cursor == {'type': 5, 'start': 0, 'done': True}
    assert result.item_errors == 0
    detailed = [o for o in result.outings if o.rating_raw]
    assert len(detailed) == 2
    assert {o.external_id for o in detailed} == {'1-26073', '1-26072'}
    assert {o.source_activity for o in result.outings} >= {'scialpinismo', 'mtb'}


# -- transports --------------------------------------------------------------


def test_fixture_post_matches_the_form_fields():
    transport = BackfillFixtureTransport(FIXTURES, 'gipfelbuch')
    response = transport.post(
        bf.GIPFELBUCH_LIST_URL,
        data={'dvf_csrf_token': 'anything', 'filter_conditions_offset': '66'},
    )
    assert response.status == 200
    assert response.json()['items']


def test_http_post_is_polite_and_budgeted():
    sent = []

    class Session:
        def post(self, url, data=None, headers=None, timeout=None):
            sent.append((url, data, headers))

            class Raw:
                status_code = 200
                headers = {}
                content = b'{}'

            Raw.url = url
            return Raw()

    sleeps = []
    clock = iter([0.0, 0.0, 0.5, 0.5, 0.5, 0.5]).__next__
    transport = BackfillHttpTransport(
        RateLimit(2.0, 2, 5), session=Session(), sleep=sleeps.append, clock=clock
    )
    transport.post('https://a.example/x', data={'k': 'v'})
    transport.post('https://a.example/x', data={'k': 'w'})
    assert sleeps == [1.5]
    assert sent[0][2]['User-Agent'] == BackfillHttpTransport.USER_AGENT
    assert 'backfill' in BackfillHttpTransport.USER_AGENT
    with pytest.raises(SourceDown, match='budget'):
        transport.post('https://a.example/x', data={})


# -- the fixtures -------------------------------------------------------------


def test_backfill_fixtures_hold_no_partner_text_nor_identity():
    """As `test_fixtures_licence` for the harvest fixtures: placeholders only."""
    import json
    import re

    from c2corg_api.partners import contract
    from c2corg_api.tests.partners.test_fixtures_licence import _free_text

    for directory in sorted(p for p in FIXTURES.iterdir() if p.is_dir()):
        manifest = json.loads((directory / 'manifest.json').read_text('utf-8'))
        for entry in manifest['entries']:
            path = directory / entry['file']
            text = path.read_text(encoding='utf-8')
            assert not re.search(r'[\w.+-]+@[\w-]+\.\w', text), path
            if path.suffix != '.json':
                continue
            data = json.loads(text)
            endpoint = contract.endpoint_of(entry['url'], manifest['source'])
            assert list(_free_text(data, manifest['source'], endpoint)) == [], path
            for item in data.get('items', []) if isinstance(data, dict) else []:
                assert 'contentpreview' not in item and 'routename' not in item
                assert re.fullmatch(r'user\d+', item.get('autor', 'user0')), path
