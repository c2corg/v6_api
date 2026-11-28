import datetime
import json
import shutil
from collections import Counter
from pathlib import Path

import pytest

from c2corg_api.partners import contract, htmlparse
from c2corg_api.partners.adapter import ParseError, SourceBlocked, SourceDown
from c2corg_api.partners.lookups import MemoryLookupCache
from c2corg_api.partners.model import FetchContext, HarvestedOuting, HarvestedRoute
from c2corg_api.partners.sources import REGISTRY, bivouak
from c2corg_api.partners.sources.bivouak import BivouakAdapter
from c2corg_api.partners.transport import FixtureTransport, HttpResponse

FIXTURES = Path(__file__).parent / 'fixtures'
LIST = 'https://www.bivouak.net/topos/liste_des_sorties.php'
FEED = 'https://www.bivouak.net/rss/outings/outings.rss'
# the outing ids of the recorded feed
FEED_IDS = [30882, 30883, 30884, 30885, 30886, 30887, 30888, 30889, 30891, 30892]
SINCE = datetime.date(2026, 2, 15)
NOW = datetime.datetime(2026, 11, 25, 8, 0, tzinfo=datetime.UTC)


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

    def lists(self):
        return [str(p['id_sport']) for u, p in self.calls if u == LIST]

    def feeds(self):
        return [u for u, _ in self.calls if u == FEED]

    def details(self):
        return [
            u.split('sortie-')[1].split('-')[0]
            for u, _ in self.calls
            if u not in (LIST, FEED)
        ]


class Canned:
    """A transport that answers the same response to everything."""

    request_count = 0

    def __init__(self, status=200, body=b'', content_type='text/html'):
        self.response = HttpResponse(
            status, {'Content-Type': content_type}, body, 'https://x'
        )

    def get(self, url, *, params=None, headers=None):
        return self.response


@pytest.fixture
def no_details(monkeypatch):
    """No detail page is fetched: the tests of the lists do not need them."""
    monkeypatch.setattr(bivouak, 'MAX_DETAIL_FETCHES', 0)


def run(transport=None, lookups=None, since=SINCE, cursor=None):
    lookups = lookups if lookups is not None else MemoryLookupCache()
    spy = Spy(
        transport
        if transport is not None
        else FixtureTransport(FIXTURES, 'bivouak', BivouakAdapter.rate)
    )
    ctx = FetchContext(
        since=since,
        now=NOW,
        cursor=cursor,
        transport=spy,
        lookups=lookups,
        secrets={},
    )
    return BivouakAdapter().fetch(ctx), spy, lookups


def by_id(result):
    return {o.external_id: o for o in result.outings}


def fixture_copy(tmp_path, **replacements):
    """A copy of the fixtures; `name=(old, new)` edits the text of a file."""
    target = tmp_path / 'bivouak'
    shutil.copytree(FIXTURES / 'bivouak', target)
    for name, (old, new) in replacements.items():
        path = target / name
        text = path.read_text(encoding='utf-8')
        assert old in text, (name, old)
        path.write_text(text.replace(old, new, 1), encoding='utf-8')
    return tmp_path


def run_copy(tmp_path, **kwargs):
    return run(FixtureTransport(tmp_path, 'bivouak'), **kwargs)


# -- the source --------------------------------------------------------------


def test_registered_and_credited():
    assert REGISTRY['bivouak'] is BivouakAdapter
    assert BivouakAdapter.name == 'bivouak'
    assert BivouakAdapter.site_name == 'bivouak.net'
    assert BivouakAdapter.site_url == 'https://www.bivouak.net'
    assert BivouakAdapter.required_secrets == ()
    # robots.txt: 10 s between two requests, and a request budget for the run
    assert BivouakAdapter.rate.min_interval_s >= 10
    assert BivouakAdapter.rate.max_requests_per_run == (
        1 + 5 + bivouak.MAX_DETAIL_FETCHES
    )


def test_fixtures_are_recorded_not_synthetic():
    manifest = json.loads((FIXTURES / 'bivouak' / 'manifest.json').read_text())
    assert manifest['synthetic'] is False
    assert {e['file'] for e in manifest['entries']} == {
        p.name for p in (FIXTURES / 'bivouak').glob('*.*ml')
    }


def test_one_list_per_sport_and_the_detail_cap():
    result, spy, lookups = run()
    # the first run: the feed, then every list
    assert spy.calls[0] == (FEED, {})
    assert spy.lists() == ['1', '2', '8', '4', '16']
    # the cap, the sports taking turns (ski, hiking, mountain biking,
    # paragliding; no recent snowshoeing), the newest of each first
    assert spy.details() == [
        '30061',
        '30886',
        '30888',
        '30889',
        '29975',
        '30885',
        '30876',
        '30887',
        '29958',
        '30883',
    ]
    assert len(spy.details()) == bivouak.MAX_DETAIL_FETCHES
    assert spy.request_count == 1 + 5 + bivouak.MAX_DETAIL_FETCHES
    assert result.item_errors == 0
    # the recording keeps 3 cards per list (RECORD_LIMITS); no recent
    # snowshoeing
    assert len(result.outings) == 12
    # the others are deferred, and counted
    assert result.skipped == {'location_deferred': 2, 'too_old': 3}
    # the ids of the feed, when the lists were read, the sports still to
    # look up (mountain biking and paragliding: one outing each)
    assert result.cursor == {
        'feed': FEED_IDS,
        'lists_at': NOW.isoformat(),
        'pending': [4, 16],
    }
    # every looked up outing is cached, with or without coordinates
    assert set(lookups._data) == {f'sortie:{i}' for i in spy.details()}


def test_sports_of_the_fixtures():
    result, _, _ = run()
    assert Counter(o.source_activity for o in result.outings) == {
        'ski': 3,
        'rando': 3,
        'vtt': 3,
        'parapente': 3,
    }
    activities = {o.source_activity: set() for o in result.outings}
    for o in result.outings:
        activities[o.source_activity].add(o.activities)
    assert activities == {
        'ski': {('skitouring',)},
        'rando': {('hiking',)},
        'vtt': {('mountain_biking',)},
        'parapente': {('paragliding',)},
    }
    assert not [k for k in result.skipped if k.startswith('unmapped_activity')]


# -- the outings -------------------------------------------------------------


def test_located_ski_outing():
    outing = by_id(run()[0])['30061']
    assert outing == HarvestedOuting(
        source='bivouak',
        external_id='30061',
        url='https://www.bivouak.net/topos/sortie-30061-belle-descente.html',
        title='Belle Descente ! (Vallée Blanche)',
        date=datetime.date(2026, 4, 10),
        activities=('skitouring',),
        # the recording holds pseudonyms (PSEUDONYMISE_SELECTORS)
        author='user1',
        author_url='https://www.bivouak.net/membres/user1.html',
        lang='fr',
        region='Mont-Blanc',
        source_activity='ski',
        ski_rating_min='3.1',
        ski_rating_max='3.1',
        rating_raw='3.1',
        rating_system='c2c_ski',
        steep=False,
        height_diff_up=3000,
        lon=6.896746,
        lat=45.873075,
        geom_quality='summit',
        summit_name='Vallée Blanche',
        country='FR',
        # the topo of the breadcrumb, located at the summit (the map centre)
        routes=(
            HarvestedRoute(
                external_id='73',
                title="Vallée Blanche - Depuis l'Aiguille du Midi.",
                url='https://www.bivouak.net/topos/'
                'topo-73-vallee-blanche-depuis-aiguille-midi-sport-1.html',
                summit_name='Vallée Blanche',
                lon=6.896746,
                lat=45.873075,
                geom_quality='summit',
            ),
        ),
    )


def test_located_outings_of_other_sports():
    outings = by_id(run()[0])
    walk = outings['30885']
    assert walk.activities == ('hiking',)
    assert walk.rating_raw == 'R2'
    assert walk.rating_system is None and walk.ski_rating_min is None
    assert (walk.lon, walk.lat) == (5.9743, 45.6815)
    assert walk.summit_name == 'Mont Revard'
    para = outings['30889']
    assert para.activities == ('paragliding',)
    assert para.rating_raw == 'D1/V1/A1'
    assert para.elevation_max == 1650
    assert para.height_diff_up == 950
    assert (para.geom_quality, para.region) == ('summit', 'Ecrins')
    bike = outings['30876']
    assert bike.activities == ('mountain_biking',)
    assert bike.rating_raw == '3/3'


def test_outing_over_the_cap_keeps_the_location_hints(monkeypatch):
    monkeypatch.setattr(bivouak, 'MAX_DETAIL_FETCHES', 0)
    result, spy, _ = run()
    assert spy.details() == []
    outing = by_id(result)['30061']
    assert (outing.lon, outing.lat, outing.geom_quality) == (None, None, 'none')
    # the massif of the list, the summit named in the title, the country
    assert outing.region == 'Mont-Blanc'
    assert outing.summit_name == 'Vallée Blanche'
    assert outing.country == 'FR'
    assert result.skipped['location_deferred'] == len(result.outings)


def test_title_without_summit_has_no_summit_hint(monkeypatch):
    monkeypatch.setattr(bivouak, 'MAX_DETAIL_FETCHES', 0)
    outing = by_id(run()[0])['29958']
    assert outing.title == 'Croix de Chamrousse depuis Le Recoin ou Roche Béranger.'
    assert outing.summit_name is None
    assert outing.region == 'Belledonne'
    assert outing.ski_rating_min == '1.2'


def test_cached_lookups_are_never_asked_again(monkeypatch):
    first, spy, lookups = run()
    asked = set(spy.details())
    monkeypatch.setattr(bivouak, 'MAX_DETAIL_FETCHES', 0)
    again, spy2, _ = run(lookups=lookups)
    assert spy2.details() == []  # the cap is spent, the cache answers
    located = {o.external_id for o in again.outings if o.lat is not None}
    assert located == {o.external_id for o in first.outings if o.lat is not None}
    assert asked >= located


def test_the_cap_applies_per_run(monkeypatch):
    monkeypatch.setattr(bivouak, 'MAX_DETAIL_FETCHES', 3)
    result, spy, _ = run()
    assert spy.details() == ['30061', '30886', '30888']
    assert result.skipped['location_deferred'] == len(result.outings) - 3


def test_detail_without_a_map_is_not_located_but_is_cached():
    result, spy, lookups = run()
    untitled = by_id(result)['30886']
    assert untitled.title == 'Sortie du 18-11-2026'  # an empty link on the site
    assert (untitled.lat, untitled.geom_quality) == (None, 'none')
    assert untitled.region is None  # no massif either
    assert lookups.get('sortie:30886') == {
        'lat': None,
        'lng': None,
        'summit': None,
        'massif': None,
        'topo': None,
    }
    assert untitled.routes == ()


def test_map_without_a_summit_is_a_route_point(tmp_path):
    directory = fixture_copy(
        tmp_path,
        **{
            'sortie_30061_belle_descente.html': (
                '<a href="../topos/sommet-71-vallee-blanche.html">',
                '<a href="../topos/topo-73-x.html">',
            )
        },
    )
    outing = by_id(run_copy(directory)[0])['30061']
    assert outing.geom_quality == 'route'
    assert (outing.lon, outing.lat) == (6.896746, 45.873075)


def test_bad_coordinates_are_not_used(tmp_path):
    directory = fixture_copy(
        tmp_path,
        **{
            'sortie_30061_belle_descente.html': (
                'data-lat="45.873075"',
                'data-lat="145.5"',
            )
        },
    )
    outing = by_id(run_copy(directory)[0])['30061']
    assert (outing.lon, outing.lat, outing.geom_quality) == (None, None, 'none')


def test_gone_detail_page_is_cached_empty(tmp_path):
    fixture_copy(tmp_path)
    path = tmp_path / 'bivouak' / 'manifest.json'
    manifest = json.loads(path.read_text())
    for entry in manifest['entries']:
        if entry['file'] == 'sortie_30061_belle_descente.html':
            entry['status'] = 404
    path.write_text(json.dumps(manifest))
    result, _, lookups = run_copy(tmp_path)
    assert by_id(result)['30061'].lat is None
    assert lookups.get('sortie:30061')['lat'] is None


def test_failing_detail_page_is_not_cached(tmp_path):
    fixture_copy(tmp_path)
    path = tmp_path / 'bivouak' / 'manifest.json'
    manifest = json.loads(path.read_text())
    for entry in manifest['entries']:
        if entry['file'] == 'sortie_30061_belle_descente.html':
            entry['status'] = 404 + 96  # 500: not a page, try again next run
    path.write_text(json.dumps(manifest))
    # a 5xx on a detail page fails that outing only: it keeps its hints
    result, _, lookups = run_copy(tmp_path)
    outing = by_id(result)['30061']
    assert (outing.lat, outing.geom_quality) == (None, 'none')
    assert outing.region
    assert result.skipped['lookup_failed'] == 1
    assert lookups.get('sortie:30061') is None
    # the other detail pages were read
    assert any(o.geom_quality != 'none' for o in result.outings)


def test_missing_detail_fixture_fails_the_outing_only(tmp_path):
    fixture_copy(tmp_path)
    path = tmp_path / 'bivouak' / 'manifest.json'
    manifest = json.loads(path.read_text())
    manifest['entries'] = [
        e
        for e in manifest['entries']
        if e['file'] != 'sortie_30061_belle_descente.html'
    ]
    path.write_text(json.dumps(manifest))
    result, _, _ = run_copy(tmp_path)  # "no fixture": SourceDown for that page
    assert by_id(result)['30061'].lat is None
    assert result.skipped['lookup_failed'] == 1


def test_blocked_detail_page_stops_the_run(tmp_path):
    fixture_copy(tmp_path)
    path = tmp_path / 'bivouak' / 'manifest.json'
    manifest = json.loads(path.read_text())
    for entry in manifest['entries']:
        if entry['file'] == 'sortie_30061_belle_descente.html':
            entry['status'] = 429
    path.write_text(json.dumps(manifest))
    with pytest.raises(SourceBlocked):
        run_copy(tmp_path)


# -- multi-activity ----------------------------------------------------------


def test_multi_sport_card_has_every_activity(no_details, tmp_path):
    directory = fixture_copy(
        tmp_path,
        **{
            'liste_des_sorties_id_sport8.html': (
                'data-sport="8" id="sortie_20454"',
                'data-sport="9" id="sortie_20454"',  # ski and snowshoe
            )
        },
    )
    result, _, _ = run_copy(directory, since=datetime.date(2000, 1, 1))
    outing = by_id(result)['20454']
    assert outing.activities == ('skitouring', 'snowshoeing')
    assert outing.source_activity == 'ski+raquettes'
    assert outing.rating_raw == 'R2'  # a snowshoe rating: not a ski one
    assert outing.rating_system is None
    assert outing.date == datetime.date(2023, 3, 22)
    snowshoe = Counter(
        o.activities for o in result.outings if 'snowshoeing' in o.activities
    )
    assert snowshoe[('snowshoeing',)] == 2


def test_report_abroad_has_the_country(no_details, tmp_path):
    directory = fixture_copy(
        tmp_path,
        **{
            'liste_des_sorties_id_sport8.html': (
                '<a href="../topos/massif-16-devoluy.html">\n             Dévoluy',
                '<a href="../topos/massif-99-norvege.html">\n             Norvège',
            )
        },
    )
    result, _, _ = run_copy(directory, since=datetime.date(2000, 1, 1))
    # a report abroad: the "massif" is the country
    assert (by_id(result)['20454'].region, by_id(result)['20454'].country) == (
        'Norvège',
        'NO',
    )
    assert by_id(result)['20453'].country == 'FR'


def test_unmapped_sports_are_counted(no_details, tmp_path):
    directory = fixture_copy(
        tmp_path,
        **{
            'liste_des_sorties_id_sport1.html': (
                'data-sport="1" id="sortie_30061"',
                'data-sport="33" id="sortie_30061"',  # ski + an unknown bit
            ),
            'liste_des_sorties_id_sport2.html': (
                'data-sport="2" id="sortie_30886"',
                'data-sport="64" id="sortie_30886"',  # only unknown
            ),
        },
    )
    result, _, _ = run_copy(directory)
    assert result.skipped['unmapped_activity:32'] == 1
    assert result.skipped['unmapped_activity:64'] == 1
    assert by_id(result)['30061'].activities == ('skitouring',)
    assert '30886' not in by_id(result)


def test_every_site_sport_is_mapped():
    from c2corg_api.partners import normalise

    assert {
        c: normalise.map_activity('bivouak', c) for c in bivouak.SPORTS.values()
    } == {
        'ski': (('skitouring',), False),
        'rando': (('hiking',), False),
        'raquettes': (('snowshoeing',), False),
        'vtt': (('mountain_biking',), False),
        'parapente': (('paragliding',), False),
    }


# -- ratings -----------------------------------------------------------------


def test_steep_ski_rating(no_details, tmp_path):
    directory = fixture_copy(
        tmp_path,
        **{'liste_des_sorties_id_sport1.html': ('3.1', '4.2')},
    )
    outing = by_id(run_copy(directory)[0])['30061']
    assert outing.ski_rating_min == outing.ski_rating_max == '4.2'
    assert outing.steep is True


def test_unknown_ski_rating_stays_raw(no_details, tmp_path):
    directory = fixture_copy(
        tmp_path,
        **{'liste_des_sorties_id_sport1.html': ('3.1', 'D2')},
    )
    outing = by_id(run_copy(directory)[0])['30061']
    assert outing.rating_raw == 'D2'
    assert outing.ski_rating_min is None and outing.rating_system is None
    assert outing.steep is False


# -- skipped and failing -----------------------------------------------------


def test_old_outings_are_skipped(no_details):
    result, _, _ = run(since=datetime.date(2026, 11, 1))
    assert {o.source_activity for o in result.outings} == {'rando', 'vtt', 'parapente'}
    assert len(result.outings) == 8
    assert result.skipped['too_old'] == 7


def test_an_outing_in_two_lists_is_kept_once(no_details, tmp_path):
    directory = fixture_copy(
        tmp_path,
        **{
            # the same outing in the lists of two sports
            'liste_des_sorties_id_sport2.html': (
                'id="sortie_30886"',
                'id="sortie_30061"',
            )
        },
    )
    result, _, _ = run_copy(directory)
    assert result.skipped['duplicate'] == 1
    assert len({o.external_id for o in result.outings}) == len(result.outings)
    assert by_id(result)['30061'].source_activity == 'ski'  # the first list wins


def test_unparsable_card_counts_as_an_item_error(no_details, tmp_path):
    directory = fixture_copy(
        tmp_path,
        **{'liste_des_sorties_id_sport1.html': ('10-04-2026', 'dix avril')},
    )
    result, _, _ = run_copy(directory)
    assert result.item_errors == 1
    assert '30061' not in by_id(result)
    assert 'parse_error' not in result.skipped  # counted once
    assert len(by_id(result)) == 11


def test_bad_sport_mask_is_an_item_error(no_details, tmp_path):
    directory = fixture_copy(
        tmp_path,
        **{
            'liste_des_sorties_id_sport1.html': (
                'data-sport="1" id="sortie_30061"',
                'data-sport="x" id="sortie_30061"',
            )
        },
    )
    assert run_copy(directory)[0].item_errors == 1


def test_page_without_a_list_is_a_parse_error():
    with pytest.raises(ParseError, match='no list'):
        run(Canned(200, b'<html><body><p>Maintenance</p></body></html>'))


def test_empty_list_is_not_an_error():
    body = b'<html><body><div class="bk-lt"></div></body></html>'
    result, spy, _ = run(Canned(200, body))
    assert result.outings == [] and spy.request_count == 0
    assert spy.lists() == ['1', '2', '8', '4', '16']


def test_http_error_on_a_list_is_a_parse_error():
    with pytest.raises(ParseError, match='HTTP 404'):
        run(Canned(404, b'not found'))


# -- the feed: which lists a run reads ---------------------------------------


def cursor_of(feed=FEED_IDS, age=datetime.timedelta(hours=1), pending=()):
    return {
        'feed': list(feed),
        'lists_at': (NOW - age).isoformat(),
        'pending': list(pending),
    }


def test_nothing_new_in_the_feed_reads_no_list():
    cursor = cursor_of()
    result, spy, _ = run(cursor=cursor)
    assert spy.calls == [(FEED, {})]  # one request instead of five
    assert result.outings == []
    assert result.cursor == cursor  # the same feed, the lists of an hour ago


def test_new_outings_of_the_feed_read_the_lists_of_their_sports():
    # 30892 (ski) and 30888 (mountain biking) were not in the last feed
    result, spy, _ = run(
        cursor=cursor_of([i for i in FEED_IDS if i not in (30888, 30892)])
    )
    assert spy.lists() == ['1', '4']
    assert {o.source_activity for o in result.outings} == {'ski', 'vtt'}
    assert result.cursor['feed'] == FEED_IDS
    # only some lists were read: the date of the full read stays
    assert result.cursor['lists_at'] == (NOW - datetime.timedelta(hours=1)).isoformat()
    # the page of 30871 is not in the recording: its list is read next run
    assert result.cursor['pending'] == [4]


def test_lists_with_outings_to_look_up_are_read_again():
    lookups = MemoryLookupCache()
    for i in ('30889', '30887'):
        lookups.put(f'sortie:{i}', bivouak._extract_detail(None))
    result, spy, _ = run(cursor=cursor_of(pending=[16]), lookups=lookups)
    assert spy.lists() == ['16']
    assert spy.details() == ['30884']  # the one not looked up yet
    # its page failed (not in the recording): asked again next run
    assert result.skipped['lookup_failed'] == 1
    assert result.cursor['pending'] == [16]
    lookups.put('sortie:30884', bivouak._extract_detail(None))
    result, spy, _ = run(cursor=result.cursor, lookups=lookups)
    assert spy.lists() == ['16'] and spy.details() == []
    assert result.cursor['pending'] == []  # done: the next run reads no list


def test_every_list_is_read_again_after_a_while():
    result, spy, _ = run(cursor=cursor_of(age=bivouak.LIST_MAX_AGE))
    assert spy.lists() == ['1', '2', '8', '4', '16']
    assert result.cursor['lists_at'] == NOW.isoformat()


@pytest.mark.parametrize(
    'cursor',
    [
        None,
        {'x': 1},  # an older cursor
        cursor_of(feed=[1, 2, 3]),  # nothing in common: outings may be missed
        {**cursor_of(), 'lists_at': 'yesterday'},
        {**cursor_of(), 'lists_at': '2026-11-25T07:00:00'},  # not aware
    ],
)
def test_every_list_is_read_without_a_usable_cursor(no_details, cursor):
    assert run(cursor=cursor)[1].lists() == ['1', '2', '8', '4', '16']


def test_a_new_sport_name_in_the_feed_reads_every_list(no_details, tmp_path):
    directory = fixture_copy(tmp_path, **{'outings_rss.xml': ('[VTT]', '[Escalade]')})
    cursor = cursor_of([i for i in FEED_IDS if i != 30888])
    assert run_copy(directory, cursor=cursor)[1].lists() == ['1', '2', '8', '4', '16']


def test_sports_of_the_feed():
    words = {
        'Ski de Rando': 1,
        'Rando / Trail': 2,
        'Raquettes': 8,
        'VTT': 4,
        'Parapente': 16,
        'Ski + Raquettes': 1,
    }
    for category, bit in words.items():
        lowered = category.lower()
        assert next(b for w, b in bivouak.FEED_SPORTS if w in lowered) == bit


@pytest.mark.parametrize('status', [404, 503])
def test_a_failing_feed_reads_every_list(no_details, tmp_path, status):
    fixture_copy(tmp_path)
    path = tmp_path / 'bivouak' / 'manifest.json'
    manifest = json.loads(path.read_text())
    assert manifest['entries'][0]['url'] == FEED
    manifest['entries'][0]['status'] = status
    path.write_text(json.dumps(manifest))
    cursor = cursor_of()
    result, spy, _ = run_copy(tmp_path, cursor=cursor)
    assert spy.lists() == ['1', '2', '8', '4', '16']
    assert len(result.outings) == 12
    # the last feed is kept, to compare with the next one
    assert result.cursor['feed'] == cursor['feed']


def test_a_feed_without_items_reads_every_list(no_details, tmp_path):
    directory = fixture_copy(tmp_path)
    (directory / 'bivouak' / 'outings_rss.xml').write_text('<rss></rss>')
    assert run_copy(directory, cursor=cursor_of())[1].lists() == [
        '1',
        '2',
        '8',
        '4',
        '16',
    ]


def test_challenge_page_is_blocked(tmp_path):
    fixture_copy(tmp_path)
    shutil.copy(
        FIXTURES / 'gulliver' / 'challenge_403.html',
        tmp_path / 'bivouak' / 'challenge_403.html',
    )
    path = tmp_path / 'bivouak' / 'manifest.json'
    manifest = json.loads(path.read_text())
    manifest['entries'][0].update(
        status=403, file='challenge_403.html', content_type='text/html'
    )
    path.write_text(json.dumps(manifest))
    with pytest.raises(SourceBlocked):
        run_copy(tmp_path)


def test_site_down(tmp_path):
    fixture_copy(tmp_path)
    path = tmp_path / 'bivouak' / 'manifest.json'
    manifest = json.loads(path.read_text())
    assert manifest['entries'][1]['url'] == LIST
    manifest['entries'][1].update(status=503)
    path.write_text(json.dumps(manifest))
    with pytest.raises(SourceDown):
        run_copy(tmp_path)


# -- the HTML contract -------------------------------------------------------


def test_endpoint_names_of_the_site():
    assert contract.endpoint_of(LIST) == 'liste_des_sorties'
    assert contract.endpoint_of(FEED) == 'outings_rss'
    assert (
        contract.endpoint_of('https://www.bivouak.net/topos/sortie-30061-x-y.html')
        == 'sortie'
    )
    assert contract.endpoint_of('https://www.bivouak.net/topos/sortie-30886-.html') == (
        'sortie'
    )
    # unchanged for the JSON sources
    assert contract.endpoint_of('https://x.fr/wp-json/g/mobile/routes') == 'routes'
    assert contract.endpoint_of('https://skitour.fr/api/sorties') == 'sorties'


def test_every_html_fixture_is_trimmed_to_the_selectors():
    directory = FIXTURES / 'bivouak'
    manifest = json.loads((directory / 'manifest.json').read_text())
    for entry in manifest['entries']:
        text = (directory / entry['file']).read_text(encoding='utf-8')
        selectors = contract.read_selectors(
            'bivouak', contract.endpoint_of(entry['url'])
        )
        assert selectors, entry['file']
        assert htmlparse.trim(text, selectors) == text, entry['file']


def test_trim_drops_narratives_and_media():
    page = (
        '<html><body><main><article class="post_sortie" id="sortie_1" data-sport="1">'
        '<img src="x.jpg"><p class="bk-card__text">A long narrative.</p>'
        '<span class="bk-pill"><i><img src="y.png"></i>Ski</span>'
        '<!-- hidden --><script>alert(1)</script>'
        '<a class="bk-author" href="m" style="--c:red">Luc<img src="a.jpg"></a>'
        '</article><p>footer text</p></main></body></html>'
    )
    selectors = ['article.post_sortie .bk-pill', 'article.post_sortie a.bk-author']
    out = htmlparse.trim(page, selectors)
    assert 'narrative' not in out and 'footer' not in out and 'hidden' not in out
    assert '<img' not in out and 'script' not in out and 'style=' not in out
    assert 'Ski' in out and 'Luc' in out
    assert 'data-sport="1"' in out and 'id="sortie_1"' in out
    assert htmlparse.trim(out, selectors) == out  # idempotent
    assert htmlparse.matches(out, selectors) == dict.fromkeys(selectors, 'str')
    assert htmlparse.matches(out, ['.nothing']) == {}


def test_trim_pseudonymises_the_authors():
    card = (
        '<article class="post_sortie" id="sortie_{n}">'
        '<a class="bk-author" href="../membres/profile-{n}-{slug}.html" title="{name}">'
        '<span class="bk-av"><img src="a.jpg">{initials}</span>{name}</a>'
        '<span class="bk-pill">Ski</span></article>'
    )
    page = '<html><body><main>{}</main></body></html>'.format(
        card.format(n=44, slug='pila', name='Michel Pila', initials='MP')
        + card.format(n=1, slug='luc', name='Luc', initials='L')
        + card.format(n=45, slug='pila', name='Michel Pila', initials='MP')
    )
    selectors = ['article.post_sortie .bk-pill', 'article.post_sortie a.bk-author']
    names = {}
    out = htmlparse.trim(page, selectors, selectors[1:], names)
    assert 'Pila' not in out and 'Luc' not in out and 'pila' not in out
    assert 'MP' not in out and 'title=' not in out
    authors = htmlparse.parse(out).select('a.bk-author')
    assert [htmlparse.text_of(a) for a in authors] == ['user1', 'user2', 'user1']
    assert [a['href'] for a in authors] == [
        '../membres/user1.html',
        '../membres/user2.html',
        '../membres/user1.html',
    ]
    # idempotent, and the names are shared by the pages of a recording
    assert htmlparse.trim(out, selectors, selectors[1:], {}) == out
    other = htmlparse.trim(page.replace('Luc', 'Anne'), selectors, selectors[1:], names)
    assert 'user3' in other
    # through the recorder: the selectors of the adapter
    body = contract.trim_body('bivouak', LIST, page.encode(), {}).decode()
    assert 'Pila' not in body and 'user2' in body


def test_a_recording_keeps_the_first_cards_and_feed_items():
    card = (
        '<article class="bk-card post_sortie" data-sport="1" id="sortie_{n}">'
        '<span class="bk-pill">Ski</span></article>'
    )
    page = '<html><body><main>{}</main></body></html>'.format(
        ''.join(card.format(n=n) for n in range(5))
    )
    body = contract.trim_body('bivouak', LIST, page.encode()).decode()
    assert [a['id'] for a in htmlparse.parse(body).select(bivouak.CARD)] == [
        'sortie_0',
        'sortie_1',
        'sortie_2',
    ]
    assert (
        htmlparse.trim(body, contract.read_selectors('bivouak', 'liste_des_sorties'))
        == body
    )
    item = (
        '<item><guid>https://www.bivouak.net/topos/sortie-{n}-x.html</guid>'
        '<title><![CDATA[Un titre]]></title><author>Michel Pila</author>'
        '<description><![CDATA[<p>Un long récit</p>]]></description>'
        '<category><![CDATA[Parapente]]></category></item>'
    )
    feed = (
        '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
        '<title>Dernières sorties</title>{}</channel></rss>'
    ).format(''.join(item.format(n=n) for n in range(12)))
    body = contract.trim_body('bivouak', FEED, feed.encode()).decode()
    assert 'Pila' not in body and 'récit' not in body and 'titre' not in body
    soup = htmlparse.parse(body)
    assert len(soup.select('item > guid')) == 10
    assert htmlparse.text_of(soup.select_one('item > category')) == 'Parapente'


def test_trim_body_keeps_other_bodies_as_they_are():
    url = 'https://www.bivouak.net/robots.txt'
    assert contract.trim_body('bivouak', url, b'<html>oops</html>') == (
        b'<html>oops</html>'
    )
    assert contract.trim_body('bivouak', LIST, b'{"a": 1}') == b'{}\n'


def test_shapes_report_a_selector_that_stopped_matching():
    adapter = BivouakAdapter()
    expected = contract.fixture_shapes(FIXTURES / 'bivouak')
    assert set(adapter.REQUIRED_SELECTORS) <= set(expected)
    same = contract.compare(adapter, expected, expected)
    assert not same.breaking and not same.unchecked
    actual = {k: dict(v) for k, v in expected.items()}
    del actual['sortie']['.bk-viewer[data-lat][data-lng]']
    report = contract.compare(adapter, expected, actual)
    assert report.breaking
    assert report.problems == [
        'sortie: .bk-viewer[data-lat][data-lng] no longer matches'
    ]
    assert any(
        '- .bk-viewer[data-lat][data-lng]' in line for line in report.diff['sortie']
    )
    # an endpoint that was not requested can not be checked
    del actual['sortie']
    assert not contract.compare(adapter, expected, actual).breaking


def test_captured_shapes_of_a_run_match_the_fixtures():
    transport = contract.CapturingTransport(
        FixtureTransport(FIXTURES, 'bivouak', BivouakAdapter.rate)
    )
    contract.run_adapter(BivouakAdapter(), transport, {}, SINCE, NOW)
    report = contract.compare(
        BivouakAdapter(),
        contract.fixture_shapes(FIXTURES / 'bivouak'),
        contract.captured_shapes('bivouak', transport.responses),
    )
    assert not report.breaking and not report.unchecked


# -- the tool of the lookups -------------------------------------------------


def test_extract_detail():
    detail = bivouak._extract_detail(
        '<ol class="bk-crumbs"><li><a href="../topos/massif-9-mont-blanc.html">'
        'Mont-Blanc</a></li><li><a href="../topos/sommet-71-x.html">Un Sommet</a>'
        '</li></ol><div class="bk-viewer" data-lat="45.5" data-lng="6.5"></div>'
    )
    assert detail == {
        'lat': 45.5,
        'lng': 6.5,
        'summit': 'Un Sommet',
        'massif': 'Mont-Blanc',
        'topo': None,
    }
    assert bivouak._extract_detail('<p>nothing</p>')['lat'] is None
    assert (
        bivouak._extract_detail(
            '<div class="bk-viewer" data-lat="0" data-lng="0"></div>'
        )['lng']
        is None
    )
    assert (
        bivouak._extract_detail('<div class="bk-viewer" data-lat="a" data-lng="b">')[
            'lat'
        ]
        is None
    )
    assert bivouak._extract_detail(None)['lat'] is None


def test_extract_detail_topo():
    detail = bivouak._extract_detail(
        '<ol class="bk-crumbs"><li><a href="../topos/sommet-71-x.html">Un Sommet</a>'
        '</li><li><a href="../topos/topo-73-un-sommet-par-ici-sport-1.html">'
        'Par ici.</a></li></ol>'
    )
    assert detail['topo'] == {
        'id': '73',
        'title': 'Par ici.',
        'url': 'https://www.bivouak.net/topos/topo-73-un-sommet-par-ici-sport-1.html',
    }
    # no map: the route has no position
    assert bivouak._route(detail) == HarvestedRoute(
        external_id='73',
        title='Un Sommet - Par ici.',
        url='https://www.bivouak.net/topos/topo-73-un-sommet-par-ici-sport-1.html',
        summit_name='Un Sommet',
    )
    # a link without an id, or without a text, is no topo
    for crumb in (
        '<a href="../topos/topo-x.html">Par ici</a>',
        '<a href="../topos/topo-73-x.html"> </a>',
    ):
        html = f'<ol class="bk-crumbs"><li>{crumb}</li></ol>'
        assert bivouak._extract_detail(html)['topo'] is None
    # the details cached before the topos were read have no `topo`
    assert bivouak._route({'lat': 45.5, 'lng': 6.5, 'summit': 'S'}) is None


def test_routes_of_the_fixtures():
    outings = by_id(run()[0])
    routes = {i: [r.external_id for r in o.routes] for i, o in outings.items()}
    # every detail page with a topo in its breadcrumb; the others have none
    assert {i: r for i, r in routes.items() if r} == {
        '29958': ['281'],
        '30061': ['73'],
        '30876': ['6639'],
        '30883': ['6757'],
        '30885': ['4653'],
        '30887': ['5350'],
        '30888': ['6834'],
        '30889': ['6310'],
    }
    walk = outings['30885'].routes[0]
    assert (
        walk.title
        == 'Mont Revard - Par le golet de la Pierre, retour par la Crémaillère'
    )
    assert (walk.lon, walk.lat, walk.geom_quality) == (5.9743, 45.6815, 'summit')
