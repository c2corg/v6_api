import datetime
import json
from collections import Counter
from pathlib import Path

import pytest

from c2corg_api.partners import contract, htmlparse
from c2corg_api.partners.adapter import ParseError, SourceBlocked, SourceDown
from c2corg_api.partners.lookups import MemoryLookupCache
from c2corg_api.partners.model import FetchContext, HarvestedOuting, HarvestedRoute
from c2corg_api.partners.sources import REGISTRY
from c2corg_api.partners.sources.gipfelbuch import (
    LIST_URL,
    MAX_DETAIL_FETCHES,
    GipfelbuchAdapter,
    parse_detail,
    parse_region,
    route_key,
    split_title,
    summit_key,
)
from c2corg_api.partners.transport import FixtureTransport, HttpResponse

FIXTURES = Path(__file__).parent / 'fixtures'
SINCE = datetime.date(2026, 11, 18)
NOW = datetime.datetime(2026, 11, 25, 9, 0, tzinfo=datetime.UTC)
DETAIL_FIXTURES = 15  # the summit pages recorded next to the listing
RESOLVED = 16  # outings of those summits (two reports can share one)
OUTINGS = 35  # the reports of the window


class Spy:
    def __init__(self, inner):
        self.inner = inner
        self.urls = []

    @property
    def request_count(self):
        return self.inner.request_count

    def get(self, url, *, params=None, headers=None):
        self.urls.append(url)
        return self.inner.get(url, params=params, headers=headers)

    def details(self):
        return [u for u in self.urls if u != LIST_URL]


class Canned:
    """A transport that answers the listing with a page and details with `detail`."""

    request_count = 0

    def __init__(self, listing, detail=None, status=200):
        self.listing = listing
        self.detail = detail
        self.status = status
        self.urls = []

    def get(self, url, *, params=None, headers=None):
        self.urls.append(url)
        if url == LIST_URL:
            body, status = self.listing, self.status
        elif isinstance(self.detail, Exception):
            raise self.detail
        else:
            body, status = self.detail or '', 200 if self.detail else 404
        return HttpResponse(
            status, {'Content-Type': 'text/html; charset=UTF-8'}, body.encode(), url
        )


def run(transport=None, lookups=None, since=SINCE, cursor=None):
    lookups = lookups if lookups is not None else MemoryLookupCache()
    spy = Spy(
        transport
        if transport is not None
        else FixtureTransport(FIXTURES, 'gipfelbuch', GipfelbuchAdapter.rate)
    )
    ctx = FetchContext(
        since=since, now=NOW, cursor=cursor, transport=spy, lookups=lookups, secrets={}
    )
    return GipfelbuchAdapter().fetch(ctx), spy, lookups


def by_id(result):
    return {o.external_id: o for o in result.outings}


def card(
    report_id='1',
    slug='skitour-gipfel-2000m',
    label='Skitour',
    title='Gipfel (2000m)',
    regions=('CH - Wallis', 'Schweiz'),
    date='24.11.2026',
    author='Anna',
    route=None,
):
    route_cell = f'<div class="dv-tt">{route}</div>' if route else ''
    cells = ''.join(f'<div class="dv-tt">{r}</div>' for r in regions)
    return (
        f'<article class="item list-item y2026" id="conditions{report_id}">'
        f'<a href="/verhaeltnisse/{report_id}-{slug}">'
        '<div class="item_inner"><div class="listcontent">'
        f'<span class="column main-icon"><i data-tooltip="{label}"></i></span>'
        f'<span class="column main-title"><div class="main">{title}</div>'
        f'{route_cell}</span>'
        f'<span class="column regions">{cells}</span>'
        '<span class="column information">'
        f'<span class="date" data-tooltip="Datum Tour: {date}">{date}</span>'
        '<div class="autor-infos">'
        f'<span data-tooltip="Autor: {author}">{author}</span></div></span>'
        '</div></div></a></article>'
    )


def page(*cards):
    body = ''.join(cards)
    return f'<html><body><div id="conditions-container">{body}</div></body></html>'


MAP = (
    '<div id="map-container-inner" data-lat="46.5" data-lon="8.25" '
    'data-zoom="15"></div>'
)
# a report page with the link of its route in the heading
ROUTE_MAP = (
    '<div class="page-title"><div><h2>'
    '<a href="/routen/21390-gipfel-2000m-nordflanke">Gipfel (2000m): Nordflanke</a>'
    '</h2></div></div>' + MAP
)


def test_registered_and_credited():
    assert REGISTRY['gipfelbuch'] is GipfelbuchAdapter
    assert GipfelbuchAdapter.name == 'gipfelbuch'
    assert GipfelbuchAdapter.site_name == 'gipfelbuch.ch'
    assert GipfelbuchAdapter.site_url == 'https://www.gipfelbuch.ch'
    assert GipfelbuchAdapter.required_secrets == ()
    rate = GipfelbuchAdapter.rate
    assert rate.max_requests_per_run >= 1 + MAX_DETAIL_FETCHES


def test_fixture_outings():
    result, spy, lookups = run()
    assert len(result.outings) == OUTINGS
    assert result.item_errors == 0
    assert result.skipped == Counter(too_old=31, summit_lookup_deferred=19)
    assert spy.urls[0] == LIST_URL
    assert len(spy.details()) == MAX_DETAIL_FETCHES == DETAIL_FIXTURES
    assert result.cursor is None
    assert by_id(result)['2355428'] == HarvestedOuting(
        source='gipfelbuch',
        external_id='2355428',
        url='https://www.gipfelbuch.ch/verhaeltnisse/2355428',
        title='Riedbergerhorn (1787m)',
        date=datetime.date(2026, 11, 24),
        activities=('skitouring',),
        author='user4',  # pseudonymised in the recording
        lang='de',
        region='D - Allgäu',
        source_activity='skitour',
        elevation_max=1787,
        summit_name='Riedbergerhorn',
        country='DE',
        lon=10.1592,
        lat=47.4517,
        geom_quality='summit',
        # the route named under the summit; its page is linked from the report
        # page read for the summit
        routes=(
            HarvestedRoute(
                external_id='name:riedbergerhorn|1787|von grasgehren',
                title='Riedbergerhorn: von Grasgehren',
                url='https://www.gipfelbuch.ch/routen/4634-riedbergerhorn-1787m-von-grasgehren',
                summit_name='Riedbergerhorn',
                elevation_max=1787,
                lon=10.1592,
                lat=47.4517,
                geom_quality='summit',
            ),
        ),
    )
    hike = by_id(result)['2355522']
    assert (hike.activities, hike.source_activity) == (('hiking',), 'wanderung')
    assert (hike.summit_name, hike.elevation_max) == ('Pyramidenspitze', 1998)
    assert (hike.region, hike.country, hike.author) == ('A - Tirol', 'AT', 'user3')
    assert (hike.lon, hike.lat, hike.geom_quality) == (12.2767, 47.6103, 'summit')
    assert lookups.get('summit:riedbergerhorn_1787') == {
        'lat': 47.4517,
        'lon': 10.1592,
        'route': {
            'url': 'https://www.gipfelbuch.ch/routen/4634-riedbergerhorn-1787m-von-grasgehren',
            'name': 'von Grasgehren',
        },
    }


def test_routes_of_the_fixtures():
    result, _, _ = run(since=datetime.date(2026, 1, 1))
    # every report of the listing names its route under the summit
    assert all(len(o.routes) == 1 for o in result.outings)
    routes = Counter(o.routes[0].external_id for o in result.outings)
    assert len(routes) < len(result.outings)  # some routes have several reports
    with_url = [o.routes[0] for o in result.outings if o.routes[0].url]
    assert with_url
    assert all(r.url.startswith('https://www.gipfelbuch.ch/routen/') for r in with_url)
    # located routes are where their outing is
    for o in result.outings:
        assert (o.routes[0].lon, o.routes[0].lat) == (o.lon, o.lat)


def test_route_of_a_card():
    listing = page(card('1', route='Nordflanke'), card('2'))
    result, _, _ = run(Canned(listing, ROUTE_MAP))
    first, second = result.outings
    assert first.routes == (
        HarvestedRoute(
            external_id='name:gipfel|2000|nordflanke',
            title='Gipfel: Nordflanke',
            url='https://www.gipfelbuch.ch/routen/21390-gipfel-2000m-nordflanke',
            summit_name='Gipfel',
            elevation_max=2000,
            lon=8.25,
            lat=46.5,
            geom_quality='summit',
        ),
    )
    assert second.routes == ()  # a card without a route name


def test_route_of_another_report_gives_no_link():
    # the summit page read (cached) is about another route of the summit
    listing = page(card('1', route='Südgrat'))
    result, _, _ = run(Canned(listing, ROUTE_MAP))
    route = result.outings[0].routes[0]
    assert (route.external_id, route.url) == ('name:gipfel|2000|sudgrat', None)


def test_route_key():
    assert route_key('Bürglen', 2165, 'Nordflanke') == 'name:burglen|2165|nordflanke'
    assert route_key('Bürglen', None, 'Nord-Flanke!') == 'name:burglen||nord flanke'
    long = route_key('Gipfel', 2000, 'x ' * 200)
    assert len(long) == 128
    assert long != route_key('Gipfel', 2000, 'x ' * 201)


def test_outings_without_a_resolved_summit_keep_the_hints():
    result, _, _ = run()
    unresolved = [o for o in result.outings if o.geom_quality == 'none']
    assert len(unresolved) == OUTINGS - RESOLVED
    for o in unresolved:
        assert (o.lon, o.lat) == (None, None)
        assert o.summit_name
        assert o.country in {'CH', 'AT', 'DE', 'IT', 'LI'} or o.country is None


def test_every_activity_is_mapped_or_counted():
    result, _, _ = run(since=datetime.date(2026, 1, 1))
    assert len(result.outings) == 65
    assert result.skipped['unmapped_activity:ohne_routentyp'] == 1
    assert result.item_errors == 0
    activities = Counter(o.source_activity for o in result.outings)
    assert activities == Counter(
        wanderung=35, skitour=23, schneeschuhtour=4, klettertour=2, hochtour=1
    )
    by_code = {o.source_activity: o.activities for o in result.outings}
    assert by_code == {
        'wanderung': ('hiking',),
        'skitour': ('skitouring',),
        'schneeschuhtour': ('snowshoeing',),
        'klettertour': ('rock_climbing',),
        'hochtour': ('mountain_climbing',),
    }
    assert all(o.date >= datetime.date(2026, 1, 1) for o in result.outings)


def test_summits_are_looked_up_once_and_remembered():
    lookups = MemoryLookupCache()
    first, spy1, _ = run(lookups=lookups)
    assert len(spy1.details()) == MAX_DETAIL_FETCHES
    # the second run asks only for the summits not remembered yet (which the
    # fixtures do not have: the site "answers" a down error, the run goes on)
    second, spy2, _ = run(lookups=lookups)
    assert not set(spy1.details()) & set(spy2.details())
    assert len(second.outings) == OUTINGS
    assert Counter(o.geom_quality for o in second.outings) == Counter(
        summit=RESOLVED, none=OUTINGS - RESOLVED
    )
    # three summit pages fail ("no fixture"), then the rest waits for next run
    assert second.skipped['lookup_failed'] == 3
    assert second.skipped['summit_lookup_deferred'] == OUTINGS - RESOLVED - 3


def test_same_summit_in_two_reports_is_one_lookup():
    listing = page(
        card('1'),
        card('2', label='Wanderung'),
        card('3', title='Anderer (2100m)'),
    )
    result, transport, lookups = run(Canned(listing, MAP))
    assert len(transport.urls) == 3  # the listing and two summits
    assert [o.geom_quality for o in result.outings] == ['summit'] * 3
    assert (result.outings[1].lon, result.outings[1].lat) == (8.25, 46.5)
    assert lookups.get('summit:gipfel_2000') == {'lat': 46.5, 'lon': 8.25}


def test_fetch_budget_is_enforced_by_the_adapter():
    cards = [card(str(i), title=f'Gipfel{i} (2000m)') for i in range(1, 30)]
    result, transport, _ = run(Canned(page(*cards), MAP))
    assert len(transport.urls) == 1 + MAX_DETAIL_FETCHES
    assert result.skipped['summit_lookup_deferred'] == 29 - MAX_DETAIL_FETCHES
    assert len(result.outings) == 29


def test_a_summit_page_without_coordinates_is_remembered():
    listing = page(card())
    nomap = '<div id="map-container-inner" data-lat="" data-lon=""></div>'
    result, transport, lookups = run(Canned(listing, nomap))
    assert result.outings[0].geom_quality == 'none'
    assert lookups.get('summit:gipfel_2000') == {'lat': None, 'lon': None}
    _, again, _ = run(Canned(listing, nomap), lookups=lookups)
    assert again.urls == [LIST_URL]  # asked once


def test_a_failing_summit_page_is_not_remembered():
    listing = page(card('1'), card('2', title='B (2100m)'))
    result, transport, lookups = run(Canned(listing, detail=None))  # 404
    assert result.skipped['summit_lookup_failed'] == 2
    assert lookups.get('summit:gipfel_2000') is None
    assert len(result.outings) == 2


def test_site_down_on_a_summit_page_keeps_the_listing():
    listing = page(card('1'), card('2', title='B (2100m)'))
    result, transport, lookups = run(Canned(listing, SourceDown('HTTP 503')))
    # each outing keeps its hints for the job's resolver
    assert [o.summit_name for o in result.outings] == ['Gipfel', 'B']
    assert {o.geom_quality for o in result.outings} == {'none'}
    assert len(transport.urls) == 3  # the listing, then one try per summit
    assert result.skipped['lookup_failed'] == 2
    assert 'summit_lookup_deferred' not in result.skipped
    assert lookups.get('summit:gipfel_2000') is None


def test_summit_pages_stop_after_three_failures_in_a_row():
    titles = [f'S{i} ({2000 + i}m)' for i in range(5)]
    listing = page(*(card(str(i), title=t) for i, t in enumerate(titles)))
    result, transport, _ = run(Canned(listing, SourceDown('HTTP 503')))
    assert len(result.outings) == 5
    assert len(transport.urls) == 1 + 3
    assert result.skipped['lookup_failed'] == 3
    assert result.skipped['summit_lookup_deferred'] == 2


def test_blocked_on_a_summit_page_is_a_block():
    with pytest.raises(SourceBlocked):
        run(Canned(page(card()), SourceBlocked('HTTP 429')))


def test_cursor_is_kept():
    result, _, _ = run(cursor={'x': 1})
    assert result.cursor == {'x': 1}


def test_unmapped_activity_is_counted_by_its_label():
    listing = page(
        card('1', 'canyoning-schlucht-900m', 'Canyoning'),
        card('2', 'schlucht-900m', 'Anderer Routentyp'),
        card('3', 'schlucht-900m', 'Bike'),
    )
    result, _, _ = run(Canned(listing, MAP))
    assert result.skipped == Counter(
        {'unmapped_activity:canyoning': 1, 'unmapped_activity:anderer_routentyp': 1}
    )
    assert [o.activities for o in result.outings] == [('mountain_biking',)]


@pytest.mark.parametrize(
    ('label', 'expected'),
    [
        ('Skitour', 'skitouring'),
        ('Freeride', 'skitouring'),
        ('Eisklettern', 'ice_climbing'),
        ('Klettersteig', 'via_ferrata'),
        ('Bike', 'mountain_biking'),
        ('Hochtour', 'mountain_climbing'),
        ('Schneeschuhtour', 'snowshoeing'),
        ('Klettertour', 'rock_climbing'),
        ('Wanderung', 'hiking'),
    ],
)
def test_activity_from_the_icon_label(label, expected):
    result, _, _ = run(Canned(page(card('1', 'x-1000m', label)), MAP))
    assert result.outings[0].activities == (expected,)


def test_item_errors_are_counted_and_do_not_stop_the_run():
    broken = (
        card('2')
        .replace('Datum Tour: 24.11.2026', 'kein Datum')
        .replace('>24.11.2026<', '><')
    )
    no_title = card('3').replace('Gipfel (2000m)', '')
    no_id = card('5').replace('id="conditions5"', 'id="other5"')
    listing = page(card('1'), broken, no_title, card('6', title='Z (2200m)'))
    listing = listing.replace('</div></body>', no_id + '</div></body>')
    result, _, _ = run(Canned(listing, MAP))
    assert [o.external_id for o in result.outings] == ['1', '6']
    assert result.item_errors == 2  # no date, no title; `other5` is no report
    assert 'unmapped_activity' not in ''.join(result.skipped)


def test_duplicate_report_ids_are_counted():
    result, _, _ = run(Canned(page(card('1'), card('1')), MAP))
    assert len(result.outings) == 1
    assert result.skipped['duplicate'] == 1


def test_old_reports_are_skipped_before_any_lookup():
    listing = page(card('1', date='01.01.2026'), card('2', date='24.11.2026'))
    result, transport, _ = run(Canned(listing, MAP))
    assert result.skipped == Counter(too_old=1)
    assert len(transport.urls) == 2


def test_listing_without_reports_is_a_parse_error():
    with pytest.raises(ParseError, match='layout changed'):
        run(Canned('<html><body>Wartungsarbeiten</body></html>'))


def test_listing_http_error_is_a_parse_error():
    with pytest.raises(ParseError, match='HTTP 404'):
        run(Canned('', status=404))


def test_challenge_is_blocked_and_503_is_down(tmp_path):
    pages = {403: '<title>Just a moment...</title>', 503: '<h1>Wartung</h1>'}
    for status, error in ((403, SourceBlocked), (503, SourceDown)):
        root = tmp_path / str(status)
        directory = root / 'gipfelbuch'
        directory.mkdir(parents=True)
        (directory / 'x.html').write_text(pages[status])
        (directory / 'manifest.json').write_text(
            json.dumps(
                {
                    'source': 'gipfelbuch',
                    'entries': [{'url': LIST_URL, 'status': status, 'file': 'x.html'}],
                }
            )
        )
        with pytest.raises(error):
            run(FixtureTransport(root, 'gipfelbuch'))


def test_the_old_listing_url_is_not_requested():
    _, spy, _ = run()
    assert 'verhaeltnisse/uebersicht' in spy.urls[0]
    assert spy.urls[0].startswith('https://www.gipfelbuch.ch/')


# -- helpers -----------------------------------------------------------------


@pytest.mark.parametrize(
    ('title', 'expected'),
    [
        ('Regenflüeli (1582m)', ('Regenflüeli', 1582)),
        ('Pointe de Tcholeire (2440m)(2440m)', ('Pointe de Tcholeire', 2440)),
        ('Gargellen Schafbergbahn', ('Gargellen Schafbergbahn', None)),
        ('Sibe Hängste (7 Hengste) (1952m)', ('Sibe Hängste (7 Hengste)', 1952)),
        ('Hügel (9999m)', ('Hügel', None)),  # not plausible
        ('Hügel (0m)', ('Hügel (0m)', None)),
        ('(1500m)', ('(1500m)', 1500)),
    ],
)
def test_split_title(title, expected):
    assert split_title(title) == expected


@pytest.mark.parametrize(
    ('labels', 'expected'),
    [
        (['CH - Zentralschweiz', 'Schweiz'], ('CH - Zentralschweiz', 'CH')),
        (['A - Tirol', 'Österreich'], ('A - Tirol', 'AT')),
        (['D - Allgäu', 'Deutschland'], ('D - Allgäu', 'DE')),
        (['I - Piemonte', 'Italien'], ('I - Piemonte', 'IT')),
        (['F - Savoie', 'Frankreich'], ('F - Savoie', 'FR')),
        (['FL - Liechtenstein', 'Andere Region'], ('FL - Liechtenstein', 'LI')),
        (['', 'Andere Region'], (None, None)),
        (['', 'Schweiz'], (None, 'CH')),
        ([], (None, None)),
        (['X - Nirgendwo', 'Schweiz'], ('X - Nirgendwo', 'CH')),
    ],
)
def test_parse_region(labels, expected):
    assert parse_region(labels) == expected


def test_summit_key():
    assert summit_key('Riedbergerhorn', 1787) == 'summit:riedbergerhorn_1787'
    assert summit_key('Pointe de Tcholeire', None) == 'summit:pointe_de_tcholeire_x'
    assert len(summit_key('x' * 300, 2000)) == 128


def test_parse_detail():
    assert parse_detail(MAP) == {'lat': 46.5, 'lon': 8.25}
    assert parse_detail(ROUTE_MAP) == {
        'lat': 46.5,
        'lon': 8.25,
        'route': {
            'url': 'https://www.gipfelbuch.ch/routen/21390-gipfel-2000m-nordflanke',
            'name': 'Nordflanke',
        },
    }
    # a heading without a route link (a report about a hut, or no route page)
    assert parse_detail(
        '<div class="page-title"><h2><a href="/punkte/1-hut">Hut</a></h2></div>' + MAP
    ) == {'lat': 46.5, 'lon': 8.25}
    assert parse_detail('<p>no map</p>') is None
    nothing = {'lat': None, 'lon': None}
    for attrs in (
        'data-lat="" data-lon=""',
        'data-lat="abc" data-lon="1"',
        'data-lat="0" data-lon="0"',
        'data-lat="95" data-lon="8"',
        'data-lat="nan" data-lon="8"',
        '',
    ):
        assert parse_detail(f'<div id="map-container-inner" {attrs}></div>') == nothing


# -- the HTML contract ---------------------------------------------------------


def _fixture(name):
    return (FIXTURES / 'gipfelbuch' / name).read_text(encoding='utf-8')


def test_required_selectors_match_the_fixtures():
    adapter = GipfelbuchAdapter()
    for endpoint, name in (
        ('uebersicht', 'uebersicht.html'),
        ('detail', '2355428.html'),
    ):
        soup = htmlparse.parse(_fixture(name))
        for selector in adapter.REQUIRED_SELECTORS[endpoint]:
            assert soup.select_one(selector) is not None, selector
    assert len(htmlparse.parse(_fixture('uebersicht.html')).select('article')) == 66


def test_a_changed_layout_is_breaking():
    adapter = GipfelbuchAdapter()
    changed = _fixture('uebersicht.html').replace('information', 'infos')
    actual = {
        'uebersicht': htmlparse.matches(
            changed, adapter.REQUIRED_SELECTORS['uebersicht']
        )
    }
    expected = contract.fixture_shapes(FIXTURES / 'gipfelbuch')
    report = contract.compare(adapter, expected, actual)
    assert any('.information .date' in line for line in report.problems)


def test_trim_keeps_the_listing_markup_and_drops_the_narrative():
    raw = page(card('1'), card('2', 'wanderung-a-1000m')).replace(
        '<div class="item_inner">',
        '<div class="item_inner"><p>Bis zur Hütte schneefrei, Text des Autors.</p>'
        '<div class="previewtextcontainer">Mehr Text</div><img src="a.jpg">',
    )
    url = 'https://www.gipfelbuch.ch/verhaeltnisse/uebersicht'
    trimmed = contract.trim_body('gipfelbuch', url, raw.encode()).decode()
    assert 'Text des Autors' not in trimmed and 'Mehr Text' not in trimmed
    assert 'a.jpg' not in trimmed
    assert contract.trim_body('gipfelbuch', url, trimmed.encode()).decode() == trimmed
    result, _, _ = run(Canned(trimmed, MAP))
    assert [o.external_id for o in result.outings] == ['1', '2']


def test_trim_detail_keeps_the_map_only():
    detail = f'<html><body><p>Text</p>{MAP}</body></html>'.encode()
    url = 'https://www.gipfelbuch.ch/verhaeltnisse/2355428'
    trimmed = contract.trim_body('gipfelbuch', url, detail)
    assert b'Text' not in trimmed and b'data-lat="46.5"' in trimmed


def test_item_pages_are_the_detail_endpoint():
    base = 'https://www.gipfelbuch.ch/verhaeltnisse'
    assert contract.endpoint_of(f'{base}/2355428') == 'detail'
    assert contract.endpoint_of(f'{base}/uebersicht') == 'uebersicht'


def test_fixture_directory_is_a_real_recording():
    manifest = json.loads((FIXTURES / 'gipfelbuch/manifest.json').read_text())
    assert manifest['synthetic'] is False
    assert manifest['recorded_at'] == '2026-11-25'
    assert len(manifest['entries']) == 1 + DETAIL_FIXTURES
