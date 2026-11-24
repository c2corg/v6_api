import datetime
import json
import shutil
from collections import Counter
from pathlib import Path

import pytest

from c2corg_api.partners.adapter import ParseError, SourceBlocked, SourceDown
from c2corg_api.partners.lookups import MemoryLookupCache
from c2corg_api.partners.model import FetchContext, HarvestedOuting
from c2corg_api.partners.sources import REGISTRY, gulliver
from c2corg_api.partners.sources.gulliver import (
    GulliverAdapter,
    extract_route,
    title_from_slug,
)
from c2corg_api.partners.transport import FixtureTransport, HttpResponse

FIXTURES = Path(__file__).parent / 'fixtures'
BASE = 'https://www.gulliver.it/wp-json/gulliver/mobile'
SINCE = datetime.date(2026, 11, 10)
NOW = datetime.datetime(2026, 11, 24, 8, 0, tzinfo=datetime.UTC)

ROUTE_KEYS = {
    'route:57949',
    'route:55310',
    'route:60118',
    'route:62001',
    'route:59407',
    'route:44871',
    'route:52980',
}


class Spy:
    """Wraps a transport and records the requests."""

    def __init__(self, inner):
        self.inner = inner
        self.calls = []

    @property
    def request_count(self):
        return self.inner.request_count

    def get(self, url, *, params=None, headers=None):
        self.calls.append((url, dict(params or {})))
        return self.inner.get(url, params=params, headers=headers)

    def route_ids(self):
        return [str(p['id']) for u, p in self.calls if u == f'{BASE}/routes']

    def pages(self):
        return [str(p['page']) for u, p in self.calls if u == f'{BASE}/commentglobal']


class Canned:
    """A transport that answers the same response to everything."""

    request_count = 0

    def __init__(self, status=200, body=b'', content_type='application/json'):
        self.response = HttpResponse(
            status, {'Content-Type': content_type}, body, 'https://x'
        )

    def get(self, url, *, params=None, headers=None):
        return self.response


def run(transport=None, lookups=None, since=SINCE, cursor=None):
    lookups = lookups if lookups is not None else MemoryLookupCache()
    spy = Spy(
        transport
        if transport is not None
        else FixtureTransport(FIXTURES, 'gulliver', GulliverAdapter.rate)
    )
    ctx = FetchContext(
        since=since,
        now=NOW,
        cursor=cursor,
        transport=spy,
        lookups=lookups,
        secrets={},
    )
    return GulliverAdapter().fetch(ctx), spy, lookups


def by_id(result):
    return {o.external_id: o for o in result.outings}


def fixture_copy(tmp_path, **replacements):
    """A copy of the fixtures; `name=text` overwrites `<name>` files."""
    target = tmp_path / 'gulliver'
    shutil.copytree(FIXTURES / 'gulliver', target)
    for name, text in replacements.items():
        (target / name).write_text(text, encoding='utf-8')
    return tmp_path


def test_registered():
    assert REGISTRY['gulliver'] is GulliverAdapter
    assert GulliverAdapter.name == 'gulliver'
    assert GulliverAdapter.site_name == 'gulliver.it'
    assert GulliverAdapter.site_url == 'https://www.gulliver.it'
    assert GulliverAdapter.required_secrets == ()
    rate = GulliverAdapter.rate
    assert (rate.min_interval_s, rate.max_requests_per_run, rate.timeout_s) == (
        2.0,
        40,
        20,
    )


def test_manifest_is_synthetic():
    manifest = json.loads((FIXTURES / 'gulliver' / 'manifest.json').read_text())
    assert manifest['synthetic'] is True
    assert 'Cloudflare' in manifest['note']


def test_fetch_counters():
    result, spy, lookups = run()
    assert len(result.outings) == 9
    assert result.skipped == Counter(
        {
            'unmapped_activity:kayak': 1,
            'too_old': 1,
            'route_lookup_deferred': 1,
        }
    )
    assert result.item_errors == 1  # the unparsable date, not also skipped
    assert result.cursor == {'last_comment_id': 48213}
    # two pages (the second one holds a too old report: no page 3)
    assert spy.pages() == ['1', '2']
    assert all(isinstance(o, HarvestedOuting) for o in result.outings)


def test_skimo_outing_with_alpine_blachere_grade():
    outing = by_id(run()[0])['48213']
    assert outing == HarvestedOuting(
        source='gulliver',
        external_id='48213',
        url='https://www.gulliver.it/itinerari/cima-bianca-da-cheneil/#comment-48213',
        title='Cima Bianca da Cheneil',
        date=datetime.date(2026, 11, 23),
        activities=('skitouring',),
        author='giovanni-bianchi',
        author_url=None,
        lang='it',
        region='Valtournenche',
        source_activity='skimo',
        ski_rating_min='2.1',
        ski_rating_max='3.3',
        rating_raw='BSA',
        rating_system='blachere',
        steep=False,
        elevation_max=3009,
        height_diff_up=1400,
        orientations=('N', 'NE'),
        snow={'top_cm': 40, 'low_cm': 5, 'line_m': 2100},
        lon=7.6483,
        lat=45.9181,
        geom_quality='start',
    )


def test_skisteep_outing_with_entities():
    outing = by_id(run()[0])['48207']
    assert outing == HarvestedOuting(
        source='gulliver',
        external_id='48207',
        url=(
            'https://www.gulliver.it/itinerari/'
            'canalone-nord-est-del-monte-emilius/#comment-48207'
        ),
        # &#8211; unescaped; no district: the region name, &#8217; unescaped
        title='Canalone Nord-Est del Monte Emilius – variante diretta',
        date=datetime.date(2026, 11, 23),
        activities=('skitouring',),
        author='ale.guida',
        lang='it',
        region='Valle d’Aosta',
        source_activity='skisteep',
        ski_rating_min='4.1',
        ski_rating_max='5.6',
        rating_raw='OS',
        rating_system='blachere',
        steep=True,
        elevation_max=3559,
        height_diff_up=1500,
        orientations=('NE',),
        snow={'top_cm': 25, 'low_cm': 0, 'line_m': 1800},
        lon=7.3547,
        lat=45.6911,
        geom_quality='start',
    )


def test_outing_whose_route_404s_is_deferred():
    result, spy, lookups = run()
    outing = by_id(result)['48210']
    assert outing == HarvestedOuting(
        source='gulliver',
        external_id='48210',
        url=(
            'https://www.gulliver.it/itinerari/'
            'colle-del-teodulo-invernale/#comment-48210'
        ),
        title='Colle del teodulo invernale',  # from the permalink slug
        date=datetime.date(2026, 11, 23),
        activities=('skitouring',),
        author='marta_r',
        lang='it',
        source_activity='skimo',
        snow={'top_cm': 30, 'low_cm': 10, 'line_m': 1900},
    )
    assert outing.geom_quality == 'none'
    assert lookups.get('route:61022') is None  # a 404 is not cached
    assert '61022' in spy.route_ids()


def test_other_activities_and_entities():
    outings = by_id(run()[0])
    snowshoe = outings['48204']
    assert snowshoe.activities == ('snowshoeing',)
    assert snowshoe.title == 'Ciaspolata al Lago d’Arpy'
    assert snowshoe.snow == {'top_cm': 15}  # empty strings are omitted
    assert snowshoe.rating_raw is None and snowshoe.ski_rating_min is None
    assert snowshoe.orientations == ('S',)

    hike = outings['48190']
    assert hike.activities == ('hiking',)
    assert hike.title == 'Anello del Monte Fallère'
    assert hike.snow is None
    assert hike.rating_system is None

    climb = outings['48188']
    assert climb.activities == ('rock_climbing',)
    assert climb.region == 'Liguria'  # no district
    assert climb.orientations == ()
    assert climb.height_diff_up == 0

    skimo = outings['48181']
    assert skimo.region == 'Saint-Rhémy-en-Bosses'
    assert skimo.orientations == ('E', 'SE')
    assert (skimo.ski_rating_min, skimo.ski_rating_max) == ('2.1', '3.3')
    assert skimo.rating_raw == 'BS' and skimo.steep is False
    # no snow figures that are integers
    assert by_id(run()[0])['48199'].snow is None


def test_route_without_coordinates():
    outing = by_id(run()[0])['48196']
    assert outing.title == 'Punta della Valletta'
    assert outing.lon is None and outing.lat is None
    assert outing.geom_quality == 'none'
    assert outing.rating_raw == 'BS'  # the rest of the route is kept
    assert outing.elevation_max == 2830


def test_unmapped_activity_makes_no_route_request():
    result, spy, _ = run()
    assert 'unmapped_activity:kayak' in result.skipped
    assert '48185' not in by_id(result)
    assert '3333' not in spy.route_ids()


def test_too_old_stops_paging():
    result, spy, _ = run()
    assert '48102' not in by_id(result)
    assert result.skipped['too_old'] == 1
    assert '3' not in spy.pages()


def test_empty_page_stops_paging():
    # a window wide enough to read the old report: page 3 is empty
    result, spy, _ = run(since=datetime.date(2026, 1, 1))
    assert spy.pages() == ['1', '2', '3']
    assert len(result.outings) == 10
    assert result.skipped['too_old'] == 0
    assert by_id(result)['48102'].date == datetime.date(2026, 10, 2)


def test_page_limit(monkeypatch):
    monkeypatch.setattr(gulliver, 'MAX_PAGES', 1)
    result, spy, _ = run(since=datetime.date(2026, 1, 1))
    assert spy.pages() == ['1']
    assert len(result.outings) == 6


def test_one_route_request_per_distinct_route():
    result, spy, _ = run()
    ids = spy.route_ids()
    # 48213, 48199 and the too old report share route 57949
    assert sorted(ids) == sorted(set(ids))
    assert sorted(ids) == sorted(k.split(':')[1] for k in ROUTE_KEYS | {'route:61022'})
    assert spy.request_count == 2 + 8


def test_lookup_cache_miss_stores_the_extracted_dict():
    _, _, lookups = run()
    assert lookups.get('route:57949') == {
        'title': 'Cima Bianca da Cheneil',
        'region': 'Valle d&#8217;Aosta',
        'district': 'Valtournenche',
        'lat': 45.9181,
        'lng': 7.6483,
        'alt_top': 3009,
        'drop': 1400,
        'exposure': 'N-NE',
        'grade_skimo': 'BSA',
    }
    assert lookups.get('route:62001')['lat'] is None
    assert lookups.get('route:61022') is None


def test_lookup_cache_hit_avoids_the_request():
    first, _, lookups = run()
    second, spy, _ = run(lookups=lookups)
    # only 61022 (404, never cached) is asked again
    assert spy.route_ids() == ['61022']
    assert spy.request_count == 3
    assert second.outings == first.outings


def test_prefilled_cache_means_no_route_request():
    lookups = MemoryLookupCache()
    for key in ROUTE_KEYS:
        lookups.put(
            key,
            {
                'title': f'Route {key}',
                'region': 'Piemonte',
                'district': None,
                'lat': 45.0,
                'lng': 7.0,
                'alt_top': 2000,
                'drop': 800,
                'exposure': 'W',
                'grade_skimo': 'MS',
            },
        )
    lookups.put('route:61022', lookups.get('route:57949'))
    result, spy, _ = run(lookups=lookups)
    assert spy.route_ids() == []
    assert spy.request_count == 2
    outing = by_id(result)['48210']
    assert outing.title == 'Route route:57949'
    assert outing.region == 'Piemonte'
    assert outing.orientations == ('W',)
    assert outing.geom_quality == 'start'
    assert result.skipped.get('route_lookup_deferred') is None


def test_route_lookup_cap(monkeypatch):
    monkeypatch.setattr(gulliver, 'MAX_ROUTE_FETCHES', 2)
    result, spy, lookups = run()
    # 57949 and the 404 of 61022 used the budget; the others are deferred
    assert spy.route_ids() == ['57949', '61022']
    assert result.skipped['route_lookup_deferred'] == 7
    assert len(result.outings) == 9
    deferred = by_id(result)['48207']
    assert deferred.title == 'Canalone nord est del monte emilius'
    assert deferred.geom_quality == 'none'
    assert deferred.source_activity == 'skisteep'
    assert deferred.steep is True  # from the activity, not the grade
    assert lookups.get('route:55310') is None  # deferred, nothing cached
    # the report on the cached route still gets its data
    assert by_id(result)['48199'].elevation_max == 3009


def test_unknown_grade_keeps_the_raw_value(tmp_path):
    inner = json.loads((FIXTURES / 'gulliver' / 'routes_id52980.json').read_text())
    inner['meta']['data']['grade_skimo'] = '5.3'
    directory = fixture_copy(tmp_path, **{'routes_id52980.json': json.dumps(inner)})
    outing = by_id(run(FixtureTransport(directory, 'gulliver'))[0])['48181']
    assert outing.rating_raw == '5.3'
    assert outing.rating_system is None
    assert outing.ski_rating_min is None and outing.steep is False


def test_challenge_page_is_blocked(tmp_path):
    manifest_path = tmp_path / 'gulliver' / 'manifest.json'
    fixture_copy(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    for entry in manifest['entries']:
        if entry['params'] == {'page': '1'}:
            entry.update(
                status=403, file='challenge_403.html', content_type='text/html'
            )
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(SourceBlocked):
        run(FixtureTransport(tmp_path, 'gulliver'))


def test_challenge_on_a_route_request_is_blocked(tmp_path):
    fixture_copy(tmp_path)
    manifest_path = tmp_path / 'gulliver' / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    for entry in manifest['entries']:
        if entry['params'] == {'id': '55310'}:
            entry.update(
                status=403, file='challenge_403.html', content_type='text/html'
            )
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(SourceBlocked):
        run(FixtureTransport(tmp_path, 'gulliver'))


def test_challenge_fixture_is_a_cloudflare_page():
    body = (FIXTURES / 'gulliver' / 'challenge_403.html').read_text()
    assert 'Just a moment...' in body


def test_site_down(tmp_path):
    fixture_copy(tmp_path)
    manifest_path = tmp_path / 'gulliver' / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['entries'][0].update(status=503)
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(SourceDown):
        run(FixtureTransport(tmp_path, 'gulliver'))


@pytest.mark.parametrize(
    'transport',
    [
        Canned(body=b'<html>not json</html>', content_type='text/html'),
        Canned(body=b'{"code": "rest_forbidden"}'),
        Canned(status=404, body=b'{}'),
    ],
)
def test_unexpected_page_is_a_parse_error(transport):
    with pytest.raises(ParseError):
        run(transport)


def test_empty_first_page_keeps_the_cursor():
    result, _, _ = run(Canned(body=b'[]'), cursor={'last_comment_id': 48000})
    assert result.outings == []
    assert result.cursor == {'last_comment_id': 48000}
    result, _, _ = run(Canned(body=b'[]'))
    assert result.cursor is None


def test_bad_items_are_counted_not_fatal():
    items = [
        'not an object',
        {'ID': 1, 'comment_date': '2026-11-23 10:00:00'},
        {
            'ID': 2,
            'comment_date': '2026-11-23 10:00:00',
            'comment_post_ID': 'abc',
            'permalink': 'https://www.gulliver.it/itinerari/x/',
            'term': {'code': 'skimo'},
        },
    ]
    result, _, _ = run(_Paged([items, []]))
    assert result.outings == []
    assert result.item_errors == 3
    assert not result.skipped


def test_duplicate_report_on_two_pages_is_yielded_once():
    page = json.loads((FIXTURES / 'gulliver' / 'commentglobal_page1.json').read_text())
    result, spy, _ = run(_Paged([page, page[:2], []]), lookups=_filled(), since=SINCE)
    assert len(result.outings) == 6
    assert result.skipped['duplicate'] == 2


class _Paged:
    request_count = 0

    def __init__(self, pages):
        self.pages = pages

    def get(self, url, *, params=None, headers=None):
        page = self.pages[int(params['page']) - 1]
        return HttpResponse(200, {}, json.dumps(page).encode(), url)


def _filled():
    lookups = MemoryLookupCache()
    for key in ROUTE_KEYS | {'route:61022'}:
        lookups.put(key, {'title': 'T', 'region': 'R'})
    return lookups


def test_extract_route():
    assert extract_route(None) is None
    assert extract_route([]) is None
    assert extract_route({'code': 'rest_no_route'})['title'] is None
    route = extract_route(
        [
            {
                'title': {'rendered': 'Cima &amp; Colle'},
                'region': {'name': 'Piemonte'},
                'meta': {
                    'data': {'alt_top': '2500', 'drop': 'n.d.'},
                    'geo': {'coords': {'lat': '0', 'lng': '0'}},
                },
            }
        ]
    )
    # the title is stored as is, cleaned when the outing is built
    assert route['title'] == 'Cima &amp; Colle'
    assert route['alt_top'] == 2500 and route['drop'] is None
    assert route['lat'] is None and route['lng'] is None  # (0, 0) is invalid


def test_title_from_slug():
    assert title_from_slug('https://www.gulliver.it/itinerari/cima-bianca/') == (
        'Cima bianca'
    )
    assert title_from_slug('') == ''
