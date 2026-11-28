"""The gulliver.it adapter, on the real recording (2026-11-27) and on edge cases.

`fixtures/gulliver/` is a real recording (`record gulliver --since 2026-11-20`,
texts redacted, authors pseudonymised); `fixtures/gulliver_synthetic/` holds
hand-written edge cases in the same format.
"""

import datetime
import json
import shutil
from collections import Counter
from pathlib import Path

import pytest

from c2corg_api.partners.adapter import ParseError, SourceBlocked, SourceDown
from c2corg_api.partners.lookups import MemoryLookupCache
from c2corg_api.partners.model import FetchContext, HarvestedOuting, HarvestedRoute
from c2corg_api.partners.sources import REGISTRY, gulliver
from c2corg_api.partners.sources.gulliver import (
    GulliverAdapter,
    exposures,
    extract_route,
    front_page_reports,
    gpx_url,
    title_from_slug,
)
from c2corg_api.partners.transport import FixtureTransport, HttpResponse

FIXTURES = Path(__file__).parent / 'fixtures'
BASE = 'https://www.gulliver.it/wp-json/gulliver/mobile'
FRONT = 'https://www.gulliver.it/wp-json/gulliver/front_page/comments'
# `record` asked for 7 days back: the same requests come again from this day
SINCE = datetime.date(2026, 11, 20)
NOW = datetime.datetime(2026, 11, 27, 12, 0, tzinfo=datetime.UTC)


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

    def ids(self, endpoint):
        return [str(p.get('id')) for u, p in self.calls if u == f'{BASE}/{endpoint}']

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


def transport(directory='gulliver', root=FIXTURES):
    return FixtureTransport(root, directory, GulliverAdapter.rate)


def run(inner=None, lookups=None, since=SINCE):
    lookups = lookups if lookups is not None else MemoryLookupCache()
    spy = Spy(inner if inner is not None else transport())
    ctx = FetchContext(
        since=since,
        now=NOW,
        cursor=None,
        transport=spy,
        lookups=lookups,
        secrets={},
    )
    return GulliverAdapter().fetch(ctx), spy, lookups


def synthetic(**kwargs):
    return run(transport('gulliver_synthetic'), **kwargs)


def by_id(result):
    return {o.external_id: o for o in result.outings}


def edited_copy(tmp_path, change, directory='gulliver'):
    """A copy of a fixture directory, its manifest entries edited by `change`."""
    shutil.copytree(FIXTURES / directory, tmp_path / 'gulliver')
    manifest_path = tmp_path / 'gulliver' / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    for entry in manifest['entries']:
        change(entry)
    manifest_path.write_text(json.dumps(manifest))
    return FixtureTransport(tmp_path, 'gulliver', GulliverAdapter.rate)


def test_registered():
    assert REGISTRY['gulliver'] is GulliverAdapter
    assert GulliverAdapter.name == 'gulliver'
    assert GulliverAdapter.site_name == 'gulliver.it'
    assert GulliverAdapter.site_url == 'https://www.gulliver.it'
    assert GulliverAdapter.required_secrets == ()
    rate = GulliverAdapter.rate
    assert (rate.min_interval_s, rate.max_requests_per_run, rate.timeout_s) == (
        2.0,
        45,
        20,
    )
    # the budget of a run holds every request the adapter may make
    assert rate.max_requests_per_run >= (
        gulliver.MAX_PAGES
        + 1
        + gulliver.MAX_REPORT_FETCHES
        + gulliver.MAX_ROUTE_FETCHES
    )


def test_manifests():
    real = json.loads((FIXTURES / 'gulliver' / 'manifest.json').read_text())
    assert real['synthetic'] is False
    assert real['recorded_at'] == '2026-11-27'
    fake = json.loads((FIXTURES / 'gulliver_synthetic' / 'manifest.json').read_text())
    assert fake['synthetic'] is True
    assert fake['note'].startswith('SYNTHETIC EDGE CASES')


# -- the real recording --------------------------------------------------------


def test_fetch_counters():
    result, spy, lookups = run()
    assert len(result.outings) == 123
    assert result.item_errors == 0
    assert result.skipped == Counter(
        {
            'duplicate': 37,  # the pages of commentglobal overlap
            'too_old': 3,
            'route_lookup_deferred': 89,  # over the 24 route requests of a run
            'unmapped_activity:cycle': 1,
        }
    )
    assert result.cursor is None
    assert spy.pages() == ['1', '2', '3', '4', '5']
    assert len(spy.ids('comments')) == gulliver.MAX_REPORT_FETCHES - 4
    assert len(spy.ids('routes')) == gulliver.MAX_ROUTE_FETCHES
    assert spy.request_count == 41
    assert all(isinstance(o, HarvestedOuting) for o in result.outings)
    assert Counter(o.source_activity for o in result.outings) == Counter(
        climb=36,
        skimo=34,
        hike=31,
        crag=9,
        mountain=6,
        iceclimb=2,
        mtb=2,
        snowshoe=1,
        skisteep=1,
        ferrata=1,
    )


def test_ski_routes_are_looked_up_first():
    """The 24 route requests of the run all go to ski reports."""
    result, spy, lookups = run()
    ski = [o for o in result.outings if 'skitouring' in o.activities]
    located = [o for o in ski if o.geom_quality == 'start']
    assert len(located) == 34 and len(ski) == 35
    assert len(spy.ids('routes')) == gulliver.MAX_ROUTE_FETCHES
    assert all(o.geom_quality == 'none' for o in result.outings if o not in ski)


def test_skimo_outing_with_coordinates_and_grade():
    outing = by_id(run()[0])['350645']
    assert outing == HarvestedOuting(
        source='gulliver',
        external_id='350645',
        url='https://www.gulliver.it/itinerari/cialma-la-o-punta-cia-da-carello/2026/11/27/350645/',
        title='Cialma (la) o Punta Cia da Carello',
        date=datetime.date(2026, 11, 27),
        activities=('skitouring',),
        author='user1',
        lang='it',
        region='Piemonte - TO',
        country='IT',
        source_activity='skimo',
        ski_rating_min='1.1',
        ski_rating_max='2.3',
        rating_raw='MS',
        rating_system='blachere',
        steep=False,
        elevation_max=2196,
        height_diff_up=795,
        orientations=('E',),
        snow=None,
        gpx_url=None,
        texts={
            'narrative': '[text 491 chars]',
            'access': '[text 42 chars]',
            'conditions': '[text 20 chars]',
            'snow': 'top: [text 17 chars]; bottom: [text 17 chars]',
            'equipment': '[text 14 chars]',
        },
        lon=7.432798186508176,
        lat=45.4089357705333,
        geom_quality='start',
        # the route of the report (`comment_post_ID`), its page and start point
        routes=(
            HarvestedRoute(
                external_id='10191',
                title='Cialma (la) o Punta Cia da Carello',
                url='https://www.gulliver.it/itinerari/cialma-la-o-punta-cia-da-carello/',
                elevation_max=2196,
                lon=7.432798186508176,
                lat=45.4089357705333,
                geom_quality='start',
            ),
        ),
    )


def test_snow_line():
    assert by_id(run()[0])['350625'].snow == {'line_m': 1500}


def test_steep_skiing():
    outing = by_id(run()[0])['350448']
    assert outing.source_activity == 'skisteep'
    assert (
        outing.title == 'Querellet (Monte) – Monte Sises, itinerari vari della dorsale'
    )
    assert (outing.ski_rating_min, outing.ski_rating_max) == ('4.1', '4.1')
    assert (outing.rating_raw, outing.rating_system) == ('4.1', 'c2c_ski')
    assert outing.steep is True
    assert outing.orientations == ('NE',)


def test_an_os_grade_is_steep():
    outing = by_id(run()[0])['350634']
    assert outing.rating_raw == 'OS'
    assert outing.steep is True


def test_report_found_on_the_front_page_only():
    """Missed by the paging of commentglobal: read with `comments?id=`."""
    result, spy, lookups = run()
    assert '350579' in spy.ids('comments')
    outing = by_id(result)['350579']
    assert outing.activities == ('rock_climbing',)
    # the route summary of the report, its title unescaped
    assert outing.title == 'Carchio (Monte) – Natale a Gaza'
    assert outing.region == 'Toscana - MS'
    assert outing.gpx_url == (
        'https://www.gulliver.it/wp-content/uploads/2026/11/'
        '2026-11-21_3401462373_Escursione-alpinistica-komoot.gpx'
    )
    assert lookups.get('report:350579')['id'] == '350579'


def test_cached_reports_are_not_asked_again():
    lookups = MemoryLookupCache()
    first, spy, _ = run(lookups=lookups)
    asked = spy.ids('comments')
    second, spy, _ = run(lookups=lookups)
    assert not set(spy.ids('comments')) & set(asked)
    assert set(by_id(first)) <= set(by_id(second))


def test_gpx_links():
    outings = run()[0].outings
    links = [o.gpx_url for o in outings if o.gpx_url]
    assert len(links) == 7
    assert all(
        link.startswith('https://www.gulliver.it/wp-content/uploads/')
        and link.endswith('.gpx')
        for link in links
    )


def test_title_without_route_comes_from_the_link():
    outing = by_id(run()[0])['350553']  # its route was not looked up
    assert outing.title == 'Servaz lago di da veulla'
    assert outing.geom_quality == 'none'


def test_route_lookups_are_cached():
    lookups = MemoryLookupCache()
    _, spy, _ = run(lookups=lookups)
    route = lookups.get('route:88735')
    assert route == {
        'title': 'Anges (Sommet des), Fort du Gondran da Montgenèvre',
        'region': "Provence-Alpes-Côte d'Azur (FR)",
        'district': 'Hautes-Alpes',
        'lat': 44.92904607594178,
        'lng': 6.7189930079040705,
        'alt_top': 2455,
        'drop': 605,
        'exposure': 'Nord-Est',
        'grade_skimo': 'MS',
        'grade_skisteep': None,
    }
    _, spy, _ = run(lookups=lookups)
    assert '88735' not in spy.ids('routes')


def test_french_region_gives_the_country():
    outings = [o for o in run()[0].outings if o.region and '(FR)' in o.region]
    assert outings and all(o.country == 'FR' for o in outings)


def test_paging_stops_at_since():
    _, spy, _ = run(since=datetime.date(2026, 11, 26))
    assert spy.pages() == ['1']


# -- the synthetic edge cases ---------------------------------------------------


def test_synthetic_counters():
    result, spy, _ = synthetic()
    assert sorted(by_id(result)) == ['900001', '900002', '900003', '900007', '900010']
    assert result.item_errors == 2  # no ID, a date that does not parse
    assert result.skipped == Counter(
        {
            'too_old': 1,  # a front page link of October
            'report_lookup_empty': 1,  # comments?id= answers []
            'route_empty': 1,
            'unmapped_activity:skinord': 1,
            'lookup_failed': 1,  # a route answers 503
            'route_lookup_deferred': 1,
        }
    )
    assert spy.ids('comments') == ['900010', '900012']


def test_synthetic_steep_route_and_exposure():
    outing = by_id(synthetic()[0])['900001']
    assert outing.title == 'Canale – Nord del Test'
    assert (outing.ski_rating_min, outing.rating_system) == ('4.3', 'c2c_ski')
    assert outing.steep is True
    assert outing.orientations == ('NW',)
    assert outing.snow == {'line_m': 1800}
    assert outing.texts == {
        'narrative': '[text 120 chars]',
        'snow': 'top: [text 9 chars]',
    }


def test_synthetic_empty_route_and_unsafe_gpx_links():
    result, _, lookups = synthetic()
    outings = by_id(result)
    empty = outings['900002']
    assert empty.title == 'Cima di prova da test'
    assert empty.region is None and empty.geom_quality == 'none'
    assert empty.gpx_url is None  # http
    assert lookups.get('route:700002') == {'empty': True}
    elsewhere = outings['900003']
    assert elsewhere.gpx_url is None  # not on gulliver.it
    assert elsewhere.orientations == ()  # Varie
    assert elsewhere.geom_quality == 'none'  # (0, 0)
    assert elsewhere.snow is None  # 'abc'
    assert elsewhere.country == 'FR'


def test_synthetic_failing_route_keeps_the_outing():
    outing = by_id(synthetic()[0])['900007']
    assert outing.activities == ('mountain_biking',)
    assert outing.geom_quality == 'none'


def test_synthetic_report_of_the_front_page():
    outing = by_id(synthetic()[0])['900010']
    assert outing.gpx_url == (
        'https://www.gulliver.it/wp-content/uploads/2026/11/solo-qui.gpx'
    )
    assert outing.title == 'Canale – Nord del Test'  # the route wins


def test_empty_report_detail_is_cached():
    lookups = MemoryLookupCache()
    synthetic(lookups=lookups)
    assert lookups.get('report:900012') == {'id': None}
    _, spy, _ = synthetic(lookups=lookups)
    assert spy.ids('comments') == []


def test_report_budget(monkeypatch):
    monkeypatch.setattr(gulliver, 'MAX_REPORT_FETCHES', 1)
    result, spy, _ = synthetic()
    assert spy.ids('comments') == ['900010']
    assert result.skipped['report_lookup_deferred'] == 1


def test_route_budget(monkeypatch):
    monkeypatch.setattr(gulliver, 'MAX_ROUTE_FETCHES', 1)
    result, spy, _ = synthetic()
    # the route of the ski reports first
    assert spy.ids('routes') == ['700001']


# -- failures -----------------------------------------------------------------


def test_front_page_failure_degrades_only(tmp_path):
    def down(entry):
        if entry['url'] == FRONT:
            entry.update(status=503)

    result, _, _ = run(edited_copy(tmp_path, down, 'gulliver_synthetic'))
    assert result.skipped['lookup_failed'] == 2
    assert '900010' not in by_id(result)
    assert '900001' in by_id(result)


def test_front_page_without_content(tmp_path):
    def broken(entry):
        if entry['url'] == FRONT:
            entry['file'] = 'commentglobal_page2.json'  # []

    result, _, _ = run(edited_copy(tmp_path, broken, 'gulliver_synthetic'))
    assert result.skipped['front_page_unusable'] == 1


def test_challenge_page_is_blocked(tmp_path):
    def challenge(entry):
        if entry.get('params') == {'page': '1'}:
            entry.update(
                status=403, file='challenge_403.html', content_type='text/html'
            )

    with pytest.raises(SourceBlocked):
        run(edited_copy(tmp_path, challenge))


def test_challenge_on_a_route_request_is_blocked(tmp_path):
    def challenge(entry):
        if entry.get('params') == {'id': '88735'}:
            entry.update(
                status=403, file='challenge_403.html', content_type='text/html'
            )

    with pytest.raises(SourceBlocked):
        run(edited_copy(tmp_path, challenge))


def test_challenge_fixture_is_a_cloudflare_page():
    body = (FIXTURES / 'gulliver' / 'challenge_403.html').read_text()
    assert 'Just a moment...' in body


def test_site_down(tmp_path):
    def down(entry):
        if entry.get('params') == {'page': '1'}:
            entry.update(status=503)

    with pytest.raises(SourceDown):
        run(edited_copy(tmp_path, down))


@pytest.mark.parametrize(
    'inner',
    [
        Canned(body=b'<html>'),
        Canned(body=b'"text"'),
        Canned(status=404, body=b'{}'),
    ],
)
def test_unexpected_page_is_a_parse_error(inner):
    with pytest.raises(ParseError):
        run(inner)


def test_empty_first_page():
    class Empty(Canned):
        def get(self, url, *, params=None, headers=None):
            if url.endswith('/commentglobal'):
                return HttpResponse(200, {}, b'[]', url)
            return HttpResponse(200, {}, b'{"content": ""}', url)

    result, _, _ = run(Empty())
    assert result.outings == [] and result.item_errors == 0


# -- helpers ------------------------------------------------------------------


def test_title_from_slug():
    assert (
        title_from_slug(
            'https://www.gulliver.it/itinerari/cima-bianca-da-cheneil/2026/11/26/350636/'
        )
        == 'Cima bianca da cheneil'
    )
    assert title_from_slug('https://www.gulliver.it/itinerari/punta_x/') == 'Punta x'
    assert title_from_slug('https://www.gulliver.it/itinerari/') == ''
    assert title_from_slug(None) == ''


@pytest.mark.parametrize(
    ('raw', 'expected'),
    [
        ('Nord', ('N',)),
        ('Nord-Est', ('NE',)),
        ('Sud - Ovest', ('SW',)),
        ('nord-ovest', ('NW',)),
        ('Est, Sud-Est', ('E', 'SE')),
        ('Nord e Est', ('N', 'E')),
        ('Varie', ()),
        ('Tutte', ()),
        ('NE', ('NE',)),
        ('', ()),
        (None, ()),
    ],
)
def test_exposures(raw, expected):
    assert exposures(raw) == expected


@pytest.mark.parametrize(
    ('tracks', 'expected'),
    [
        ([{'guid': 'https://www.gulliver.it/wp-content/uploads/2026/11/a.gpx'}], True),
        ([{'guid': 'https://gulliver.it/wp-content/uploads/a.GPX'}], True),
        ([{'guid': 'http://www.gulliver.it/a.gpx'}], False),
        ([{'guid': 'https://www.gulliver.it.evil.example/a.gpx'}], False),
        ([{'guid': 'https://user@www.gulliver.it/a.gpx'}], False),
        ([{'guid': 'https://www.gulliver.it:8443/a.gpx'}], False),
        ([{'guid': 'https://www.gulliver.it/a.jpg'}], False),
        ([{'guid': 'https://www.gulliver.it/' + 'a' * 500 + '.gpx'}], False),
        ([{'guid': 'https://www.gulliver.it:bad/a.gpx'}], False),
        ([{'guid': None}], False),
        ([], False),
        (None, False),
        ('x', False),
    ],
)
def test_gpx_url(tracks, expected):
    assert (gpx_url(tracks) is not None) is expected


def test_extract_route_skeleton_and_garbage():
    assert extract_route({'1': {'title': '', 'meta': {'data': []}}}) == {'empty': True}
    assert extract_route([]) is None
    assert extract_route('x') is None


def test_front_page_reports():
    html = (
        '<a class="btn-ghost" href="https://www.gulliver.it/itinerari/x/2026/11/26/7/">'
        'a</a><a class="btn-ghost" href="https://www.gulliver.it/itinerari/x/2026/13/26/8/">'
        'b</a><a class="other" href="https://www.gulliver.it/itinerari/x/2026/11/26/9/">'
        'c</a><a class="btn-ghost" href="https://www.gulliver.it/itinerari/x/2026/11/26/7/">'
    )
    assert front_page_reports({'content': html}) == [('7', datetime.date(2026, 11, 26))]
    with pytest.raises(ValueError):
        front_page_reports([])


def test_routes_of_the_fixtures():
    outings = run()[0].outings
    # every report names its route (`comment_post_ID`): one route each
    assert all(len(o.routes) == 1 for o in outings)
    routes = Counter(o.routes[0].external_id for o in outings)
    # several reports of the recording follow the same route
    assert len(routes) < len(outings)
    assert routes.most_common(1)[0][1] >= 2
    for o in outings:
        route = o.routes[0]
        assert route.url and o.url.startswith(route.url)
        assert route.title == o.title
        if o.geom_quality == 'start':
            assert (route.lon, route.lat) == (o.lon, o.lat)
        else:  # the route was not looked up: no position, no elevation
            assert (route.lon, route.lat, route.geom_quality) == (None, None, 'none')


def test_route_url():
    assert (
        gulliver.route_url(
            'https://www.gulliver.it/itinerari/cima-bianca/2026/11/26/350636/'
        )
        == 'https://www.gulliver.it/itinerari/cima-bianca/'
    )
    for link in (
        'https://www.gulliver.it/itinerari/2026/11/26/350636/',
        'https://www.gulliver.it/itinerari/cima-bianca/',
        'https://example.org/itinerari/cima-bianca/2026/11/26/350636/',
        'https://www.gulliver.it/news/cima-bianca/2026/11/26/350636/',
        None,
    ):
        assert gulliver.route_url(link) is None
