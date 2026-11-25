import datetime
import json
import shutil
from collections import Counter
from pathlib import Path

import pytest

from c2corg_api.partners import contract, htmlparse, region_map
from c2corg_api.partners.adapter import ParseError, SourceBlocked, SourceDown
from c2corg_api.partners.lookups import MemoryLookupCache
from c2corg_api.partners.model import FetchContext, HarvestedOuting
from c2corg_api.partners.sources import REGISTRY, skitourenportal
from c2corg_api.partners.sources.skitourenportal import (
    SkitourenportalAdapter,
    parse_listing,
    summit_hint,
)
from c2corg_api.partners.transport import FixtureTransport, HttpResponse

FIXTURES = Path(__file__).parent / 'fixtures'
BASE = 'https://skitourenportal.eu'
SINCE = datetime.date(2026, 5, 1)
NOW = datetime.datetime(2026, 11, 25, 12, 0, tzinfo=datetime.UTC)


class Spy:
    """Wraps a transport and records the requests."""

    def __init__(self, inner):
        self.inner = inner
        self.calls = []

    @property
    def request_count(self):
        return self.inner.request_count

    def get(self, url, *, params=None, headers=None):
        self.calls.append((url.removeprefix(BASE + '/'), dict(params or {})))
        return self.inner.get(url, params=params, headers=headers)


class Canned:
    """A transport that answers the same response to everything."""

    request_count = 0

    def __init__(self, status=200, body=b'', content_type='text/html'):
        self.response = HttpResponse(status, {'Content-Type': content_type}, body, BASE)

    def get(self, url, *, params=None, headers=None):
        return self.response


def run(transport=None, since=SINCE, cursor=None):
    spy = Spy(
        transport
        if transport is not None
        else FixtureTransport(FIXTURES, 'skitourenportal', SkitourenportalAdapter.rate)
    )
    ctx = FetchContext(
        since=since,
        now=NOW,
        cursor=cursor,
        transport=spy,
        lookups=MemoryLookupCache(),
        secrets={},
    )
    return SkitourenportalAdapter().fetch(ctx), spy


def page(rows='', markers='', nxt=False):
    """A minimal portal page, with the shapes of the real one."""
    return (
        '<html><body><div class="overflow-y-auto h-96">'
        '<table class="w-full border-collapse border-none text-sm"><tbody>'
        f'{rows}</tbody></table>'
        f'<script>{markers}</script>'
        + ('<a href="?page=2" rel="next">next</a>' if nxt else '')
        + '</body></html>'
    )


def row(tour_id, date='15.11.2026', title='Gabler', state='Salzburg', author='Ann'):
    return (
        f'<tr class="x" data-href="{BASE}/salzburg/beitrag/{tour_id}">'
        f'<td class="px-1.5">{date}</td><td class="px-1.5">{state}</td>'
        f'<td class="px-1.5"><a href="{BASE}/benutzer/7" title="t">{author}</a></td>'
        f'<td class="px-1.5">{title}</td></tr>'
    )


def marker(tour_id, lat, lng):
    return (
        f'markerCluster.addLayer(L.marker([{lat}, {lng}])\n'
        f".on('click', function (event) {{\n var clickedTour = new CustomEvent("
        f"'clickedTour', {{\n detail: {tour_id}\n }});\n }})\n"
        f".bindPopup('<h1>x</h1>'));"
    )


def outing_of(result, external_id):
    return next(o for o in result.outings if o.external_id == external_id)


def only_state(html, slug='salzburg'):
    """A transport serving `html` for the first state and nothing for the others."""
    empty = page().encode()

    class T(Canned):
        def get(self, url, *, params=None, headers=None):
            body = html.encode() if url.endswith('/' + slug) else empty
            return HttpResponse(200, {'Content-Type': 'text/html'}, body, url)

    return T()


# -- the recorded fixtures --------------------------------------------------


def test_fixture_listing_is_parsed():
    result, spy = run()
    assert len(result.outings) == 22
    assert result.item_errors == 0
    assert result.skipped == Counter(too_old=74)
    assert result.cursor == {'last_id': 35754}
    # 5 states, and the second page of Salzburg only
    assert [c[0] for c in spy.calls] == [
        'salzburg',
        'salzburg',
        'oberoesterreich',
        'niederoesterreich',
        'kaernten',
        'steiermark',
    ]
    assert spy.calls[1][1] == {'page': 2}
    assert spy.request_count <= SkitourenportalAdapter.rate.max_requests_per_run


def test_a_tour_with_marker_and_summit():
    result, _ = run()
    assert outing_of(result, '35739') == HarvestedOuting(
        source='skitourenportal',
        external_id='35739',
        url=f'{BASE}/salzburg/beitrag/35739',
        title='Hochkönig 2941 m',
        date=datetime.date(2026, 5, 24),
        activities=('skitouring',),
        # pseudonymised in the recording (PSEUDONYMISE_SELECTORS)
        author='user1',
        author_url=f'{BASE}/benutzer/user1',
        lang='de',
        region='Salzburg',
        elevation_max=2941,
        lon=13.062194823433,
        lat=47.420375565718,
        geom_quality='route',
        summit_name='Hochkönig',
        country='AT',
    )


def test_a_tour_without_position_keeps_region_and_country():
    result, _ = run()
    o = outing_of(result, '35719')
    assert (o.title, o.region, o.country) == (
        'Die Top-Bilder 2025/26',
        'Salzburg',
        'AT',
    )
    assert (o.lat, o.lon, o.geom_quality) == (None, None, 'none')
    assert (o.summit_name, o.elevation_max) == (None, None)


def test_every_tour_is_a_ski_tour_in_austria():
    result, _ = run(since=datetime.date(2000, 1, 1))
    assert {o.activities for o in result.outings} == {('skitouring',)}
    assert {o.country for o in result.outings} == {'AT'}
    assert {o.lang for o in result.outings} == {'de'}
    assert {o.region for o in result.outings} == set(skitourenportal.STATES.values())
    assert all(o.url.startswith(BASE + '/') for o in result.outings)
    assert all(o.rating_raw is None and not o.steep for o in result.outings)


def test_a_tour_listed_on_another_page_gets_its_marker():
    """35722 has a marker on the page of another state, not on its own."""
    result, _ = run()
    positioned = {o.external_id for o in result.outings if o.geom_quality == 'route'}
    assert {'35722', '35725', '35724'} <= positioned


def test_the_cursor_is_the_highest_tour_id():
    result, _ = run(cursor={'last_id': 1})
    assert result.cursor == {'last_id': 35754}


def test_since_stops_the_paging_and_skips_old_tours():
    result, spy = run(since=datetime.date(2026, 11, 1))
    assert [o.external_id for o in result.outings] == ['35754', '35752', '35753']
    assert [c[0] for c in spy.calls] == [
        'salzburg',
        'oberoesterreich',
        'niederoesterreich',
        'kaernten',
        'steiermark',
    ]


def test_without_a_tour_the_previous_cursor_is_kept():
    result, _ = run(
        only_state(page()), since=datetime.date(2026, 11, 1), cursor={'last_id': 7}
    )
    assert result.outings == []
    assert result.cursor == {'last_id': 7}
    result, _ = run(only_state(page()), cursor=None)
    assert result.cursor is None


# -- parsing ---------------------------------------------------------------


def test_the_parser_does_not_depend_on_attribute_order_or_whitespace():
    html = (
        '<TABLE class="border-collapse   w-full">\n<tbody>\n'
        f'<tr\n data-href="{BASE}/salzburg/beitrag/5" class="a b">\n'
        '<td>\n 01.02.2026 </td><td>Salzburg</td><td><a title="t" href="/benutzer/9">'
        'Ann&nbsp;B</a></td><td>  Gabler\n 2.100 m </td></tr></tbody></TABLE>'
        '<script type="text/javascript">'
        "L.marker( [ 47.5 ,13.5 ] ).on( 'click', function(){ "
        "new CustomEvent('clickedTour', { detail:5 }) })</script>"
    )
    result, _ = run(only_state(html), since=datetime.date(2026, 1, 1))
    assert result.outings == [
        HarvestedOuting(
            source='skitourenportal',
            external_id='5',
            url=f'{BASE}/salzburg/beitrag/5',
            title='Gabler 2.100 m',
            date=datetime.date(2026, 2, 1),
            activities=('skitouring',),
            author='Ann B',
            author_url=f'{BASE}/benutzer/9',
            lang='de',
            region='Salzburg',
            elevation_max=2100,
            lat=47.5,
            lon=13.5,
            geom_quality='route',
            summit_name='Gabler',
            country='AT',
        )
    ]


def test_photo_markers_are_not_tour_markers():
    photo = (
        "L.marker([47.1, 12.1], {icon: photoIcon}).bindPopup('<img>');"
        'clickedTour detail: 9'
    )
    _, markers, _ = parse_listing(page(markers=photo))
    assert markers == {}


def test_the_titles_are_plain_text():
    html = page(row(5, title='<b>Gabler</b> &amp; Co&nbsp;<i>x</i>'))
    result, _ = run(only_state(html), since=datetime.date(2026, 1, 1))
    assert result.outings[0].title == 'Gabler & Co x'


def test_a_duplicate_id_is_kept_once():
    html = page(row(5) + row(5, title='Other'))
    result, _ = run(only_state(html), since=datetime.date(2026, 1, 1))
    assert [o.title for o in result.outings] == ['Gabler']
    assert result.skipped == Counter(duplicate=1)


def test_a_bad_row_is_an_item_error_not_a_skip():
    html = page(
        row(5)
        + row(6, date='31.02.2026')
        + row(7, date='soon')
        + '<tr data-href="/x"><td>1</td></tr>'
        + row(8, title='  ')
    )
    result, _ = run(only_state(html), since=datetime.date(2026, 1, 1))
    assert [o.external_id for o in result.outings] == ['5']
    assert result.item_errors == 4
    assert result.skipped == Counter()


@pytest.mark.parametrize(
    ('lat', 'lng'),
    [('0', '0'), ('99', '13'), ('47.1', '181'), ('10.5', '13'), ('47', '30')],
)
def test_a_marker_out_of_the_alps_is_not_a_position(lat, lng):
    html = page(row(5), marker(5, lat, lng))
    result, _ = run(only_state(html), since=datetime.date(2026, 1, 1))
    o = result.outings[0]
    assert (o.lat, o.lon, o.geom_quality) == (None, None, 'none')
    assert result.skipped == Counter(bad_coordinates=1)


def test_the_next_page_is_followed_until_the_date_is_old():
    class Pages(Canned):
        def get(self, url, *, params=None, headers=None):
            n = (params or {}).get('page', 1)
            body = {
                1: page(row(9, date='10.03.2026'), nxt=True),
                2: page(row(8, date='01.03.2026'), nxt=True),
                3: page(row(7, date='01.01.2026')),
            }[n]
            if not url.endswith('/salzburg'):
                body = page()
            return HttpResponse(200, {}, body.encode(), url)

    result, spy = run(Pages(), since=datetime.date(2026, 1, 1))
    # never more than MAX_PAGES pages of a state
    assert [c for c in spy.calls if c[0] == 'salzburg'] == [
        ('salzburg', {}),
        ('salzburg', {'page': 2}),
    ]
    assert [o.external_id for o in result.outings] == ['9', '8']


def test_the_request_budget_covers_the_worst_case():
    assert (
        len(skitourenportal.STATES) * skitourenportal.MAX_PAGES
        <= SkitourenportalAdapter.rate.max_requests_per_run
    )


# -- summit hints ----------------------------------------------------------


@pytest.mark.parametrize(
    ('title', 'expected'),
    [
        ('Spielmann 3027', ('Spielmann', 3027)),
        ('Hochkönig 2941 m', ('Hochkönig', 2941)),
        ('Schartenkopf 2857m', ('Schartenkopf', 2857)),
        ('Johannisberg 3450m', ('Johannisberg', 3450)),
        ('Hoher Sonnblick 3.106m', ('Hoher Sonnblick', 3106)),
        ('Hochthron 1.853 m', ('Hochthron', 1853)),
        ('Kleiner Priel 2136 hm', ('Kleiner Priel', 2136)),
        ('Großer Ödstein 2.335', ('Großer Ödstein', 2335)),
        ('Hochzint, 2300m', ('Hochzint', 2300)),
        ('Gabler', None),
        ('Hochkönig Birgkar', None),
        ('Saisonstart 2026', None),  # a year
        ('Skitour 2025', None),
        ('Die Top-Bilder 2025/26', None),
        ('Gipfel 800', None),  # a bare number under 1000
        ('Gipfel 5200 m', None),
        ('Gipfel 120 m', None),
        ('1234 m', None),  # no name
        ('2 Gipfel 1500 m', None),  # a name starts with a letter
        ('U-Berg Salzburger Hochtron 1.853 m pre check ohne Schi', None),
        ('eine sehr lange Tour mit vielen Worten im Titel 2500 m', None),
        ('', None),
    ],
)
def test_summit_hint(title, expected):
    assert summit_hint(title) == expected


# -- failures --------------------------------------------------------------


def test_a_page_without_a_table_is_a_parse_error():
    with pytest.raises(ParseError, match='salzburg page 1: no listing table'):
        run(Canned(200, b'<html><body><h1>Wartung</h1></body></html>'))


def test_an_empty_table_is_not_an_error():
    result, _ = run(Canned(200, page().encode()))
    assert (result.outings, result.item_errors) == ([], 0)


def test_an_unexpected_status_is_a_parse_error():
    with pytest.raises(ParseError, match='HTTP 404'):
        run(Canned(404, b'not found'))


@pytest.mark.parametrize(
    ('status', 'body', 'error'),
    [
        (500, b'<title>Server Error</title>', SourceDown),  # what /beitrag/<id> does
        (503, b'', SourceDown),
        (403, b'<title>Just a moment...</title>', SourceBlocked),
        (429, b'', SourceBlocked),
    ],
)
def test_errors_of_the_site(tmp_path, status, body, error):
    root = tmp_path / 'f'
    directory = root / 'skitourenportal'
    directory.mkdir(parents=True)
    (directory / 'page.html').write_bytes(body)
    (directory / 'manifest.json').write_text(
        json.dumps(
            {
                'source': 'skitourenportal',
                'entries': [
                    {'url': f'{BASE}/salzburg', 'status': status, 'file': 'page.html'}
                ],
            }
        )
    )
    with pytest.raises(error):
        run(FixtureTransport(root, 'skitourenportal'))


def test_no_secret_is_needed():
    assert SkitourenportalAdapter.required_secrets == ()


# -- the recordings --------------------------------------------------------


def _html_fixtures():
    return sorted(FIXTURES.glob('skitourenportal/*.html'))


def test_the_fixtures_are_recordings_not_synthetic():
    manifest = json.loads((FIXTURES / 'skitourenportal/manifest.json').read_text())
    assert manifest['synthetic'] is False
    assert len(_html_fixtures()) == 6


SELECTORS = SkitourenportalAdapter.REQUIRED_SELECTORS['salzburg']
AUTHORS = SkitourenportalAdapter.PSEUDONYMISE_SELECTORS['salzburg']


def test_every_portal_page_reads_the_same_selectors():
    adapter = SkitourenportalAdapter
    assert set(adapter.REQUIRED_SELECTORS) == set(skitourenportal.STATES)
    assert all(v == SELECTORS for v in adapter.REQUIRED_SELECTORS.values())
    assert set(adapter.PSEUDONYMISE_SELECTORS) == set(skitourenportal.STATES)


@pytest.mark.parametrize('path', _html_fixtures(), ids=lambda p: p.name)
def test_a_recording_holds_nothing_but_what_the_adapter_reads(path):
    text = path.read_text(encoding='utf-8')
    assert htmlparse.trim(text, SELECTORS) == text
    soup = htmlparse.parse(text)
    # no photo, no narrative, no site script
    assert not soup.select('img, style, link, p, figure, h1, h3, form')
    assert 'b-cdn.net' not in text and 'Keine GPS' not in text
    assert len(text) < 40_000


@pytest.mark.parametrize('path', _html_fixtures(), ids=lambda p: p.name)
def test_authors_are_not_names(path):
    for a in htmlparse.parse(path.read_text(encoding='utf-8')).select(AUTHORS[0]):
        assert htmlparse.PSEUDONYM.fullmatch(htmlparse.text_of(a))
        assert a['href'] == f'{BASE}/benutzer/{htmlparse.text_of(a)}'


def test_a_recording_goes_through_the_recorder_trimming():
    noisy = page(
        row(5, author='Ann Schmidt') + row(6, date='bad'),
        marker(5, 47.1, 13.2),
        nxt=True,
    ).replace('<body>', '<body><img src="https://x/p.jpg"><p>Tourenbeschreibung</p>')
    out = contract.trim_body('skitourenportal', f'{BASE}/salzburg', noisy.encode())
    text = out.decode()
    assert 'Schmidt' not in text and 'Tourenbeschreibung' not in text
    assert 'title=' not in text and '<img' not in text
    assert '/benutzer/user1"' in text and '/benutzer/7' not in text
    rows, markers, has_next = parse_listing(text)
    assert len(rows) == 2 and markers == {'5': (47.1, 13.2)} and has_next
    # a page that is not a listing (error page) keeps nothing of its text
    error = b'<html><title>Server Error</title></html>'
    out = contract.trim_body('skitourenportal', f'{BASE}/salzburg', error)
    assert b'Server Error' not in out


# -- the contract with the live site ---------------------------------------


@pytest.fixture
def capture():
    adapter = SkitourenportalAdapter()
    transport = contract.CapturingTransport(
        FixtureTransport(FIXTURES, 'skitourenportal', adapter.rate)
    )
    ctx = FetchContext(
        since=SINCE,
        now=NOW,
        cursor=None,
        transport=transport,
        lookups=MemoryLookupCache(),
        secrets={},
    )
    adapter.fetch(ctx)
    return adapter, transport


def test_every_selector_the_adapter_reads_matches_the_fixtures(capture):
    adapter, transport = capture
    expected = contract.fixture_shapes(FIXTURES / 'skitourenportal')
    actual = contract.captured_shapes('skitourenportal', transport.responses)
    assert set(actual) == set(skitourenportal.STATES)
    report = contract.compare(adapter, expected, actual)
    assert report.problems == [] and report.unchecked == []


def test_a_changed_layout_is_breaking(capture):
    adapter, transport = capture
    changed = [
        HttpResponse(
            r.status,
            r.headers,
            r.body.replace(b'data-href', b'data-link').replace(b'clickedTour', b'tour'),
            r.url,
        )
        for r in transport.responses
    ]
    expected = contract.fixture_shapes(FIXTURES / 'skitourenportal')
    actual = contract.captured_shapes('skitourenportal', changed)
    report = contract.compare(adapter, expected, actual)
    assert report.breaking
    assert any('tr[data-href]' in p and 'no longer matches' in p for p in report.problems)
    assert any('clickedTour' in p for p in report.problems)


def test_no_html_answer_is_unchecked_not_breaking():
    adapter = SkitourenportalAdapter()
    expected = contract.fixture_shapes(FIXTURES / 'skitourenportal')
    report = contract.compare(adapter, expected, {})
    assert not report.breaking and report.unchecked


# -- the region table ------------------------------------------------------


def test_every_region_of_the_site_is_in_the_table():
    table = region_map.load('skitourenportal')
    for text in skitourenportal.STATES.values():
        areas = region_map.lookup('skitourenportal', text)
        assert areas is not None, text
        assert areas.country == 'AT'
        assert len(areas.area_ids) == 1
    assert len(table) == len(skitourenportal.STATES)


def test_every_region_of_the_fixtures_is_in_the_table():
    result, _ = run(since=datetime.date(2000, 1, 1))
    for o in result.outings:
        assert region_map.lookup('skitourenportal', o.region)


def test_the_table_ids_are_distinct_and_well_formed():
    data = json.loads(
        (region_map.DIRECTORY / 'skitourenportal.json').read_text(encoding='utf-8')
    )
    assert data['countries'] == {'AT': 14257}
    ids = [i for r in data['regions'].values() for i in r['area_ids']]
    assert len(ids) == len(set(ids)) == 5
    for entry in data['regions'].values():
        assert entry['country'] == 'AT'
        assert all(isinstance(i, int) and i > 0 for i in entry['area_ids'])
        assert entry['range_ids'] and not set(entry['range_ids']) & set(ids)
    assert data['coverage']['site'] and data['coverage']['range_ids']


@pytest.mark.parametrize(
    ('text', 'known'),
    [
        ('Kärnten', True),
        (' kaernten ', True),
        ('KAERNTEN', True),
        ('Karnten', True),
        ('Oberösterreich', True),
        ('Oberoesterreich', True),
        ('Niederösterreich', True),
        ('Steiermark', True),
        ('Tirol', False),
        ('', False),
        (None, False),
    ],
)
def test_region_lookup_ignores_case_accents_and_transliteration(text, known):
    assert bool(region_map.lookup('skitourenportal', text)) is known


def test_regions_are_told_apart():
    ids = {
        region_map.lookup('skitourenportal', t).area_ids
        for t in skitourenportal.STATES.values()
    }
    assert len(ids) == 5


def test_a_source_without_a_table_has_no_regions():
    assert region_map.load('skitour') == {}
    assert region_map.lookup('skitour', 'Salzburg') is None


def test_the_table_is_packaged():
    manifest = (Path(__file__).parents[3] / 'MANIFEST.in').read_text()
    assert 'c2corg_api/partners/regions' in manifest


def test_the_fixtures_copy_helper_keeps_the_directory(tmp_path):
    # the CLI tests copy the whole fixtures tree: the HTML must survive a copy
    shutil.copytree(FIXTURES / 'skitourenportal', tmp_path / 'x')
    assert len(list((tmp_path / 'x').glob('*.html'))) == 6
