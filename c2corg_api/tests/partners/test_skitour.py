"""The skitour.fr adapter, offline.

Two fixture sets: `fixtures/skitour/` is a REAL recording (2026-11-25, a real
key), `fixtures/skitour_synthetic/` is hand-written in the same (real) format and
only holds the edge cases the recording does not have (broken items, odd dates,
HTML entities, invalid coordinates...). The synthetic one is flagged
`synthetic: true`.
"""

import datetime
import json
import types
from collections import Counter
from pathlib import Path

import pytest

from c2corg_api.partners.adapter import (
    ParseError,
    SourceBlocked,
    SourceDisabled,
    SourceDown,
)
from c2corg_api.partners.lookups import MemoryLookupCache
from c2corg_api.partners.model import FetchContext, HarvestedOuting
from c2corg_api.partners.sources import REGISTRY
from c2corg_api.partners.sources.skitour import SkitourAdapter
from c2corg_api.partners.transport import FixtureTransport, HttpResponse

FIXTURES = Path(__file__).parent / 'fixtures'
NOW = datetime.datetime(2026, 11, 24, 12, 0, tzinfo=datetime.UTC)
SINCE = datetime.date(2026, 11, 22)
# the real recording
REAL_NOW = datetime.datetime(2026, 11, 25, 12, 0, tzinfo=datetime.UTC)
REAL_SINCE = datetime.date(2026, 11, 18)
SECRETS = {'SKITOUR_API_KEY': 'test-key'}
API = 'https://skitour.fr/api/sorties'


class SpyTransport:
    """Records the requests and delegates to a FixtureTransport."""

    def __init__(self, inner):
        self.inner = inner
        self.calls = []

    @property
    def request_count(self):
        return self.inner.request_count

    def get(self, url, *, params=None, headers=None):
        self.calls.append((url, dict(params or {}), dict(headers or {})))
        return self.inner.get(url, params=params, headers=headers)


class StubTransport:
    """Answers a list of bodies, one per request."""

    def __init__(self, *bodies):
        self.bodies = list(bodies)
        self.calls = []
        self.request_count = 0

    def get(self, url, *, params=None, headers=None):
        self.calls.append(dict(params or {}))
        self.request_count += 1
        body, status = self.bodies.pop(0)
        return HttpResponse(status, {}, body, url)


def spy(source='skitour_synthetic', rate=SkitourAdapter.rate):
    return SpyTransport(FixtureTransport(FIXTURES, source, rate=rate))


def ctx(transport, since=SINCE, cursor=None, secrets=SECRETS, now=NOW):
    return FetchContext(
        since=since,
        now=now,
        cursor=cursor,
        transport=transport,
        lookups=MemoryLookupCache(),
        secrets=secrets,
    )


def run(source, since, now):
    transport = spy(source)
    res = SkitourAdapter().fetch(ctx(transport, since=since, now=now))
    return types.SimpleNamespace(
        outings=res.outings,
        cursor=res.cursor,
        skipped=res.skipped,
        item_errors=res.item_errors,
        transport=transport,
    )


@pytest.fixture(scope='module')
def result():
    return run('skitour_synthetic', SINCE, NOW)


@pytest.fixture(scope='module')
def real():
    return run('skitour', REAL_SINCE, REAL_NOW)


def by_id(result):
    return {o.external_id: o for o in result.outings}


def test_registered_and_described():
    assert REGISTRY['skitour'] is SkitourAdapter
    assert SkitourAdapter.name == 'skitour'
    assert SkitourAdapter.site_name == 'skitour.fr'
    assert SkitourAdapter.site_url == 'https://skitour.fr'
    assert SkitourAdapter.required_secrets == ('SKITOUR_API_KEY',)
    rate = SkitourAdapter.rate
    assert (rate.min_interval_s, rate.max_requests_per_run, rate.timeout_s) == (
        1.1,
        10,
        20,
    )


def test_fixture_sets_are_flagged():
    real = json.loads((FIXTURES / 'skitour' / 'manifest.json').read_text())
    assert real['synthetic'] is False
    assert real['recorded_at'] == '2026-11-25'
    assert not FixtureTransport(FIXTURES, 'skitour').synthetic
    # the key is a request header: nothing of it in a manifest
    assert 'headers' not in json.dumps(real).lower()
    synthetic = json.loads(
        (FIXTURES / 'skitour_synthetic' / 'manifest.json').read_text()
    )
    assert synthetic['synthetic'] is True
    assert synthetic['note'].startswith('SYNTHETIC EDGE CASES')
    assert FixtureTransport(FIXTURES, 'skitour_synthetic').synthetic


@pytest.mark.parametrize('secrets', [{}, {'SKITOUR_API_KEY': ''}, {'OTHER': 'x'}])
def test_missing_key_disables_the_source_without_any_request(secrets):
    transport = spy()
    with pytest.raises(SourceDisabled, match='SKITOUR_API_KEY'):
        SkitourAdapter().fetch(ctx(transport, secrets=secrets))
    assert transport.calls == []


def test_request_url_params_and_key_header(result):
    # 2026-11-22 -> 2026-11-24: j=2; the page is not full, so no page 2
    assert result.transport.calls == [
        (API, {'c': 1, 'l': 200, 'j': 2, 'p': 1}, {'cle': 'test-key'})
    ]


@pytest.mark.parametrize(
    ('since', 'days'),
    [
        (datetime.date(2026, 11, 24), 1),  # same day: at least 1
        (datetime.date(2026, 11, 23), 1),
        (datetime.date(2026, 11, 14), 10),
        (datetime.date(2026, 10, 24), 31),
        (datetime.date(2026, 1, 1), 31),  # clamped
        (datetime.date(2026, 12, 1), 1),  # since in the future
    ],
)
def test_days_window_is_clamped(since, days):
    transport = spy()
    SkitourAdapter().fetch(ctx(transport, since=since))
    assert transport.calls[0][1]['j'] == days


def test_window_uses_the_paris_date():
    # 23:30 UTC on the 23rd is already the 24th in Paris
    now = datetime.datetime(2026, 11, 23, 23, 30, tzinfo=datetime.UTC)
    transport = spy()
    SkitourAdapter().fetch(ctx(transport, since=datetime.date(2026, 11, 22), now=now))
    assert transport.calls[0][1]['j'] == 2


def test_full_outing_with_summit_geometry(result):
    assert by_id(result)['112345'] == HarvestedOuting(
        source='skitour',
        external_id='112345',
        url='https://skitour.fr/sorties/112345',
        title='Pointe de la Sana, face NE',
        date=datetime.date(2026, 11, 23),
        activities=('skitouring',),
        author='montagnard38',
        author_url=None,
        lang='fr',
        region='Vanoise',
        country='FR',
        summit_name='Pointe de la Sana',
        source_activity=None,
        ski_rating_min='3.2',
        ski_rating_max='3.2',
        rating_raw='3.2',
        rating_system='c2c_ski',
        steep=False,
        elevation_max=3436,
        height_diff_up=1150,
        orientations=('NE',),
        snow=None,
        lon=6.9181,
        lat=45.4372,
        geom_quality='summit',
    )


def test_steep_outing_and_paris_date(result):
    # epoch is 22:40 UTC on the 23rd = 23:40 in Paris: still the 23rd
    o = by_id(result)['112346']
    assert o.date == datetime.date(2026, 11, 23)
    assert (o.ski_rating_min, o.ski_rating_max) == ('4.2', '4.2')
    assert o.steep is True
    assert o.orientations == ('N',)
    assert (o.lon, o.lat) == (6.2874, 44.9511)


def test_date_after_midnight_in_paris(result):
    # 23:30 UTC is 00:30 on the next day in Paris (UTC+1 in November)
    assert by_id(result)['112349'].date == datetime.date(2026, 11, 24)


def test_outing_without_rating_massif_or_summits(result):
    o = by_id(result)['112347']
    assert o == HarvestedOuting(
        source='skitour',
        external_id='112347',
        url='https://skitour.fr/sorties/112347',
        title='Petite sortie sans cotation',
        date=datetime.date(2026, 11, 22),
        activities=('skitouring',),
        author='lea.ski',
        lang='fr',
    )
    assert o.geom_quality == 'none'
    assert (o.lon, o.lat) == (None, None)


def test_two_summits_the_highest_gives_the_geometry(result):
    # a numeric string altitude ("3586") counts, and is the highest here
    o = by_id(result)['112348']
    assert o.elevation_max == 3586
    assert (o.lon, o.lat) == (6.8988, 45.3604)
    assert o.geom_quality == 'summit'
    assert o.orientations == ('E', 'SE')
    assert (o.ski_rating_min, o.steep) == ('3.1', False)


def test_highest_summit_not_listed_last_or_first(result):
    # Grand Veymont (2341 m) comes after Pas de la Ville (1900 m)
    o = by_id(result)['112355']
    assert (o.lon, o.lat) == (5.5405, 44.8388)
    assert o.elevation_max == 2341


def test_missing_latlon_keeps_the_elevation(result):
    o = by_id(result)['112349']
    assert o.geom_quality == 'none'
    assert (o.lon, o.lat) == (None, None)
    assert o.elevation_max == 3506
    assert o.ski_rating_max == '2.3'


def test_zero_zero_latlon_is_rejected(result):
    o = by_id(result)['112350']
    assert o.geom_quality == 'none'
    assert (o.lon, o.lat) == (None, None)
    assert o.elevation_max == 3178
    # "NO" is not an orientation value: dropped
    assert o.orientations == ()


def test_invalid_summit_does_not_hide_a_valid_lower_one():
    item = {
        'id': 1,
        'titre': 'Deux sommets',
        'date': '1795417920',
        'sommets': [
            {'sommet': 'Haut', 'altitude': '3000', 'lat': '200', 'lng': '0'},
            {'sommet': 'Bas', 'altitude': '2000', 'lat': '45.1', 'lng': '6.1'},
            {'sommet': 'Sans altitude', 'lat': '46.0', 'lng': '7.0'},
        ],
    }
    res = SkitourAdapter().fetch(ctx(stub([item])))
    o = res.outings[0]
    assert (o.lon, o.lat, o.geom_quality) == (6.1, 45.1, 'summit')
    assert o.elevation_max == 3000
    # the name is the one of the highest summit, even without coordinates
    assert o.summit_name == 'Haut'


def test_html_and_entities_in_title_and_author(result):
    o = by_id(result)['112351']
    assert o.title == 'Dôme des Platières & l\'aller-retour "express"'
    assert o.author == 'gérard'
    assert o.height_diff_up == 870  # numeric string
    assert o.orientations == ('N', 'NW')
    assert o.ski_rating_min == '2.2'


def test_title_is_truncated_to_300_chars():
    item = {'id': 1, 'titre': 'x' * 500, 'date': '1795417920'}
    o = SkitourAdapter().fetch(ctx(stub([item]))).outings[0]
    assert len(o.title) == 300


def test_unmappable_rating_is_kept_raw_only(result):
    o = by_id(result)['112352']
    assert o.ski_rating_min is None
    assert o.ski_rating_max is None
    assert o.rating_system is None
    assert o.rating_raw == 'ski 3'
    assert o.steep is False


def test_licensed_fields_are_never_exposed(result):
    for o in result.outings:
        assert 'LICENSED' not in repr(o)
    assert all(o.snow is None for o in result.outings)


def test_too_old_items_are_skipped(result):
    assert 'too_old' in result.skipped
    assert '112210' not in by_id(result)


def test_counters_and_outing_list(result):
    # 15 items: 1 too old, 2 broken (no titre, bad date), 12 kept
    assert result.skipped == Counter({'too_old': 1})
    assert result.item_errors == 2
    assert [o.external_id for o in result.outings] == [
        '112345',
        '112346',
        '112347',
        '112348',
        '112349',
        '112350',
        '112351',
        '112352',
        '112355',
        '112356',
        '112357',
        '112358',
    ]


def test_item_errors_do_not_stop_the_others(result):
    # 112353 has no titre and 112354 an unreadable date, but 112355 follows
    ids = by_id(result)
    assert '112353' not in ids
    assert '112354' not in ids
    assert '112355' in ids
    # nothing is also counted as skipped
    assert 'parse_error' not in result.skipped


def test_first_and_last_items_are_kept():
    items = json.loads(
        (FIXTURES / 'skitour_synthetic' / 'sorties_c1_l200_p1.json').read_text()
    )
    res = SkitourAdapter().fetch(ctx(spy()))
    assert res.outings[0].external_id == str(items[0]['id'])
    assert res.outings[-1].external_id == str(items[-1]['id'])


def test_cursor_is_the_highest_id_seen(result):
    # including the too-old and the broken items that have an id
    assert result.cursor == {'last_id': 112358}


def test_cursor_is_not_lowered_by_older_ids():
    res = SkitourAdapter().fetch(ctx(spy(), cursor={'last_id': 999999}))
    assert res.cursor == {'last_id': 999999}


def test_cursor_is_kept_when_nothing_is_seen():
    res = SkitourAdapter().fetch(ctx(stub([]), cursor={'last_id': 42}))
    assert res.outings == []
    assert res.cursor == {'last_id': 42}
    assert SkitourAdapter().fetch(ctx(stub([]))).cursor is None


def stub(*pages):
    return StubTransport(*[(json.dumps(p).encode(), 200) for p in pages])


class SmallPages(SkitourAdapter):
    PAGE_SIZE = 2


def item(i):
    return {'id': i, 'titre': f'Sortie {i}', 'date': 1795417920}


def test_paging_goes_on_while_pages_are_full_and_stops_after_a_short_one():
    transport = stub([item(1), item(2)], [item(3), item(4)], [item(5)])
    res = SmallPages().fetch(ctx(transport))
    assert [o.external_id for o in res.outings] == ['1', '2', '3', '4', '5']
    assert [(c['p'], c['l']) for c in transport.calls] == [(1, 2), (2, 2), (3, 2)]
    assert res.cursor == {'last_id': 5}


def test_paging_stops_on_an_empty_page():
    transport = stub([item(1), item(2)], [])
    res = SmallPages().fetch(ctx(transport))
    assert len(res.outings) == 2
    assert [c['p'] for c in transport.calls] == [1, 2]


def test_paging_is_bounded_by_the_request_budget():
    pages = [[item(2 * n), item(2 * n + 1)] for n in range(20)]
    transport = stub(*pages)
    res = SmallPages().fetch(ctx(transport))
    assert len(transport.calls) == SkitourAdapter.rate.max_requests_per_run
    assert len(res.outings) == 2 * SkitourAdapter.rate.max_requests_per_run


def test_full_page_then_the_empty_fixture_page_2():
    # the fixture set has an empty page 2: a page-size-15 adapter asks for it
    class FullPage(SkitourAdapter):
        PAGE_SIZE = 15

    transport = spy()
    res = FullPage().fetch(ctx(transport))
    assert [c[1]['p'] for c in transport.calls] == [1, 2]
    assert len(res.outings) == 12


def test_503_page_is_source_down():
    transport = spy('skitour_down')
    with pytest.raises(SourceDown, match='503'):
        SkitourAdapter().fetch(ctx(transport))
    # the key was sent: this is the site's answer, not a disabled source
    assert transport.calls[0][2] == {'cle': 'test-key'}


@pytest.mark.parametrize(
    'directory, message',
    [
        ('skitour_no_key', 'NO API KEY'),
        ('skitour_bad_key', 'INVALID API KEY'),
    ],
)
def test_key_errors_are_blocked(directory, message):
    # real recordings: HTTP 200 with {"ERROR": ...} instead of a list
    manifest = json.loads((FIXTURES / directory / 'manifest.json').read_text())
    assert manifest['synthetic'] is False
    transport = spy(directory)
    with pytest.raises(SourceBlocked) as error:
        SkitourAdapter().fetch(ctx(transport))
    assert str(error.value) == f'skitour API error: {message}'
    assert 'test-key' not in str(error.value)
    assert len(transport.calls) == 1


@pytest.mark.parametrize(
    'message', ['QUOTA EXCEEDED', 'ACCESS DENIED', 'too many requests', 'KEY EXPIRED']
)
def test_other_refusals_are_blocked(message):
    with pytest.raises(SourceBlocked, match=message):
        SkitourAdapter().fetch(ctx(stub({'ERROR': message})))


@pytest.mark.parametrize('message', ['DATABASE UNAVAILABLE', 'BAD DAYS', '', None, 5])
def test_unknown_error_messages_are_parse_errors(message):
    with pytest.raises(ParseError, match='skitour API error'):
        SkitourAdapter().fetch(ctx(stub({'ERROR': message})))


def test_non_list_payload_is_a_parse_error():
    for body in ({'error': 'bad key'}, 'text', 12, None):
        with pytest.raises(ParseError, match='list'):
            SkitourAdapter().fetch(ctx(stub(body)))


def test_invalid_json_is_a_parse_error():
    with pytest.raises(ParseError, match='JSON'):
        SkitourAdapter().fetch(ctx(StubTransport((b'<html>oops', 200))))


def test_unexpected_status_is_a_parse_error():
    with pytest.raises(ParseError, match='404'):
        SkitourAdapter().fetch(ctx(StubTransport((b'[]', 404))))


@pytest.mark.parametrize(
    'bad',
    [
        'not an object',
        None,
        {'titre': 'x', 'date': 1795417920},  # no id
        {'id': 'abc', 'titre': 'x', 'date': 1795417920},
        {'id': 1, 'date': 1795417920},  # no titre
        {'id': 1, 'titre': '   ', 'date': 1795417920},
        {'id': 1, 'titre': '<br>', 'date': 1795417920},
        {'id': 1, 'titre': 'x'},  # no date
        {'id': 1, 'titre': 'x', 'date': None},
        {'id': 1, 'titre': 'x', 'date': 'hier'},
        {'id': 1, 'titre': 'x', 'date': [1]},
    ],
)
def test_broken_items_count_as_item_errors(bad):
    res = SkitourAdapter().fetch(ctx(stub([bad, item(7)])))
    assert res.item_errors == 1
    assert res.skipped == Counter()
    assert [o.external_id for o in res.outings] == ['7']


def test_odd_nested_values_do_not_break_an_item():
    odd = {
        'id': 5,
        'titre': 'Bizarre',
        'date': 1795417920,
        'auteur': 'someone',
        'massif': [],
        'sommets': ['x', {'altitude': None, 'lat': 'nope'}, {'lat': 1, 'lng': None}],
        'depart': 'nowhere',
        'dif_ski': 3.2,
        'denivele': 'n/a',
        'orientation': 7,
    }
    res = SkitourAdapter().fetch(ctx(stub([odd])))
    assert res.item_errors == 0
    o = res.outings[0]
    assert (o.author, o.region, o.elevation_max, o.height_diff_up) == (
        None,
        None,
        None,
        None,
    )
    assert o.geom_quality == 'none'
    assert o.ski_rating_min == '3.2'  # a JSON number is accepted
    assert o.orientations == ()


# --- start point, location hints (synthetic edge cases) ---


def test_start_point_when_no_summit_has_coordinates(result):
    # no summit at all, `depart` known
    o = by_id(result)['112356']
    assert (o.lon, o.lat, o.geom_quality) == (6.8102, 45.3301, 'start')
    assert o.summit_name is None
    assert o.orientations == ()  # "T"


def test_summit_without_coordinates_falls_back_to_the_start_point(result):
    o = by_id(result)['112358']
    assert (o.lon, o.lat, o.geom_quality) == (7.0034, 46.0123, 'start')
    # the elevation and the name of the summit are kept
    assert (o.elevation_max, o.summit_name) == (3540, 'Aiguille du Tour')
    assert o.ski_rating_min == '4.1'
    assert o.steep is True
    assert o.country is None  # Mont Blanc straddles three countries


def test_zero_zero_start_point_gives_no_geometry(result):
    o = by_id(result)['112357']  # null `sommets`, depart 0/0
    assert (o.lon, o.lat, o.geom_quality) == (None, None, 'none')
    assert o.ski_rating_min is None and o.rating_raw is None
    assert o.orientations == ()
    assert o.country == 'CH'  # Alpes Vaudoises


def test_summit_geometry_wins_over_the_start_point():
    item = {
        'id': 1,
        'titre': 'Les deux',
        'date': '1795417920',
        'sommets': [{'sommet': 'S', 'altitude': '2000', 'lat': '45.5', 'lng': '6.5'}],
        'depart': {'lat': '45.4', 'lng': '6.4'},
    }
    o = SkitourAdapter().fetch(ctx(stub([item]))).outings[0]
    assert (o.lon, o.lat, o.geom_quality) == (6.5, 45.5, 'summit')


@pytest.mark.parametrize(
    ('massif', 'country'),
    [
        ('Vanoise', 'FR'),
        ('Alpes Vaudoises', 'CH'),
        ('Mont Blanc', None),
        ('Alpes Grées N', None),
        ('Un massif inconnu', None),
        (None, None),
    ],
)
def test_country_of_the_massif(massif, country):
    item = {
        'id': 1,
        'titre': 'x',
        'date': '1795417920',
        'massif': {'nom': massif} if massif else None,
    }
    o = SkitourAdapter().fetch(ctx(stub([item]))).outings[0]
    assert o.country == country
    assert o.region == massif


# --- the REAL recording (fixtures/skitour, 2026-11-25) ---


def test_real_recording_parses_without_errors(real):
    assert len(real.outings) == 30
    assert real.item_errors == 0
    assert real.skipped == Counter()
    assert real.cursor == {'last_id': 188900}
    # one request, `j` = 7 days, the key in the `cle` header
    assert real.transport.calls == [
        (API, {'c': 1, 'l': 200, 'j': 7, 'p': 1}, {'cle': 'test-key'})
    ]


def test_real_outing_with_a_summit(real):
    # the epoch is 23:00 UTC on the 23rd = 00:00 on the 24th in Paris (UTC+1)
    assert by_id(real)['188899'] == HarvestedOuting(
        source='skitour',
        external_id='188899',
        url='https://skitour.fr/sorties/188899',
        title='Roc Rouge > Sarvatan et Crêt Maxet',
        date=datetime.date(2026, 11, 24),
        activities=('skitouring',),
        author='Géraud',
        lang='fr',
        region='Lauzière - Cheval Noir',
        country='FR',
        summit_name='Roc Rouge',
        ski_rating_min='3.2',
        ski_rating_max='3.2',
        rating_raw='3.2',
        rating_system='c2c_ski',
        elevation_max=2375,
        height_diff_up=1500,
        orientations=('SE',),
        lon=6.3402,
        lat=45.435,
        geom_quality='summit',
    )


def test_real_outing_with_only_a_start_point(real):
    o = by_id(real)['188895']  # `sommets` is null
    assert (o.lon, o.lat, o.geom_quality) == (6.01509, 45.2651, 'start')
    assert (o.summit_name, o.elevation_max) == (None, None)
    assert o.height_diff_up == 692
    assert o.country == 'FR'


def test_real_geometry_qualities(real):
    qualities = Counter(o.geom_quality for o in real.outings)
    assert qualities == Counter({'summit': 22, 'start': 8})
    assert all(o.lon is not None and o.lat is not None for o in real.outings)


def test_real_swiss_massif(real):
    o = by_id(real)['188884']
    assert (o.region, o.country) == ('Alpes Vaudoises', 'CH')


def test_real_border_massif_has_no_country(real):
    o = by_id(real)['188872']
    assert (o.region, o.country) == ('Alpes Grées N', None)
    assert o.geom_quality == 'start'


def test_real_steep_outing(real):
    o = by_id(real)['188878']
    assert (o.ski_rating_min, o.ski_rating_max) == ('4.3', '4.3')
    assert o.steep is True
    assert [x.external_id for x in real.outings if x.steep] == ['188878']


def test_real_empty_rating_and_orientation(real):
    o = by_id(real)['188867']
    assert (o.ski_rating_min, o.rating_raw, o.rating_system) == (None, None, None)
    assert o.orientations == ()
    assert o.steep is False


def test_real_orientation_t_means_all_and_is_dropped(real):
    # "T" (toutes) is not an orientation of the c2c enum
    assert by_id(real)['188900'].orientations == ()
    assert by_id(real)['188891'].orientations == ()


def test_real_dates_are_paris_midnights(real):
    # every epoch is 23:00 UTC: the day after in Paris (UTC+1 in winter)
    assert {o.date for o in real.outings} == {
        datetime.date(2026, 11, 21),
        datetime.date(2026, 11, 23),
        datetime.date(2026, 11, 24),
    }
    assert by_id(real)['188900'].date == datetime.date(2026, 11, 21)


def test_real_recording_holds_no_licensed_text(real):
    text = (FIXTURES / 'skitour' / 'sorties_c1_l200_p1.json').read_text()
    for key in ('recit', 'cond', 'photos', 'participants', 'topos', 'gpx', 'cle'):
        assert f'"{key}"' not in text
    assert 'test-key' not in text
