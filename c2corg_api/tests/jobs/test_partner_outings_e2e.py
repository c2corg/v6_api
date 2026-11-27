"""The vertical slice, offline: the harvest job on the recorded fixtures with
the real skitour and gulliver adapters, then `GET /partner-outings`.

This is the local demo (docs/partner-outings.md) run as a test: no network, the
fixtures of c2corg_api/tests/partners/fixtures, test areas around the places of
the fixtures, and a few c2c outings next to the partner ones. Both are real
recordings: skitour of 2026-11-25, gulliver of 2026-11-27 (texts redacted).
"""

import datetime
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from c2corg_api.jobs import harvest_partner_outings as job
from c2corg_api.models.area import Area
from c2corg_api.models.area_association import AreaAssociation
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.outing import Outing, OutingLocale
from c2corg_api.models.partner_outing import PartnerOuting, PartnerSource

UTC = datetime.UTC
# gulliver was recorded on 2026-11-27, skitour on 2026-11-25: harvesting later
# shifts the dates of the outings, as the demo does every day
RECORDED = datetime.date(2026, 11, 27)
SKITOUR_RECORDED = datetime.date(2026, 11, 25)
NOW = datetime.datetime(2026, 12, 1, 12, 0, tzinfo=UTC)
TODAY = NOW.date()
SHIFT = TODAY - RECORDED
SKITOUR_SHIFT = TODAY - SKITOUR_RECORDED
EARTH = 6378137.0

SETTINGS = {
    'harvest.partners.enabled': 'false',
    'harvest.partners.skitour.enabled': 'true',
    'harvest.partners.gulliver.enabled': 'true',
    'partners.interval_minutes': '15',
    'partners.retention_days': '',  # the default: kept forever
    'partners.transport': 'fixtures',
    'partners.fixtures_dir': '',
    'partners.allow_synthetic': 'false',  # both recordings are real
}

# what the fixtures hold, by external id (lon, lat of the point; date as
# recorded; ski rating min) - see c2corg_api/tests/partners/fixtures
SKITOUR_FIXTURE = (
    Path(__file__).parent.parent / 'partners/fixtures/skitour/sorties_c1_l200_p1.json'
)
SKITOUR_ITEMS = json.loads(SKITOUR_FIXTURE.read_text(encoding='utf-8'))
SKITOUR_IN_WINDOW = {item['id'] for item in SKITOUR_ITEMS}  # 30, all with a point
# in the test Vanoise box (6.4, 45.2, 7.0, 45.5): 188891, 188874 and 188871 by
# their summit, 188880 by its start point
SKITOUR_IN_VANOISE = {'188891', '188874', '188871', '188880'}
SKITOUR_PARIS_DAY = {
    item['id']: datetime.datetime.fromtimestamp(
        int(item['date']), ZoneInfo('Europe/Paris')
    ).date()
    for item in SKITOUR_ITEMS
}
# gulliver: the first run asks from 16 days before (`since` 2026-11-11 on the
# day of the recording): 124 reports, 34 with the start point of their route
# (the ski routes are looked up first, 24 a run), 18 of them in the Aosta box
GULLIVER_COUNT = 124
# the default window of the listing (14 days) leaves out the oldest (2026-11-14)
GULLIVER_LISTED = GULLIVER_COUNT - 1
GULLIVER_IN_AOSTA = {
    *('350455', '350456', '350457', '350475', '350484', '350485', '350510'),
    *('350536', '350577', '350594', '350596', '350599', '350600', '350609'),
    *('350610', '350625', '350635', '350643'),
}
GULLIVER_STEEP = {'350448', '350609', '350634'}


def mercator(lon, lat):
    x = EARTH * math.radians(lon)
    y = EARTH * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    return x, y


def box(lon0, lat0, lon1, lat1):
    x0, y0 = mercator(lon0, lat0)
    x1, y1 = mercator(lon1, lat1)
    return f'SRID=3857;POLYGON(({x0} {y0},{x0} {y1},{x1} {y1},{x1} {y0},{x0} {y0}))'


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    # the default window of the listing ends on the day of the harvest
    monkeypatch.setattr('c2corg_api.views.partner_outings.today', lambda: TODAY)


def make_area(session, title, geom):
    area = Area(area_type='range', locales=[DocumentLocale(lang='fr', title=title)])
    area.geometry = DocumentGeometry(geom_detail=geom)
    session.add(area)
    session.flush()
    return area.document_id


def make_outing(session, title, day, area_id, activities):
    outing = Outing(
        activities=activities,
        date_start=day,
        date_end=day,
        locales=[OutingLocale(lang='fr', title=title)],
    )
    session.add(outing)
    session.flush()
    session.add(AreaAssociation(document_id=outing.document_id, area_id=area_id))
    session.flush()
    return outing.document_id


@pytest.fixture
def world(session, db_connection):
    """Two areas around the fixtures, two c2c outings, then the harvest."""
    vanoise = make_area(session, 'Vanoise', box(6.4, 45.2, 7.0, 45.5))
    aosta = make_area(session, "Vallee d'Aoste", box(7.0, 45.6, 7.8, 46.0))
    c2c_skiing = make_outing(
        session,
        'Sortie c2c en Vanoise',
        TODAY - datetime.timedelta(days=1),
        vanoise,
        ['skitouring'],
    )
    c2c_hiking = make_outing(
        session,
        'Rando c2c en Vallee d Aoste',
        TODAY - datetime.timedelta(days=2),
        aosta,
        ['hiking'],
    )
    session.commit()
    job.harvest_partner_outings(SETTINGS, now=NOW)
    return {
        'vanoise': vanoise,
        'aosta': aosta,
        'c2c_skiing': f'c2c:{c2c_skiing}',
        'c2c_hiking': f'c2c:{c2c_hiking}',
    }


def listing(client, **params):
    params.setdefault('limit', 200)  # every item of the window
    return client.get('/partner-outings', params=params, status=200).json


def ids(answer):
    return [item['id'] for item in answer['items']]


def external(answer, source):
    return {
        item['id'].split(':', 1)[1]
        for item in answer['items']
        if item['source'] == source
    }


def test_harvested_outings_are_listed_with_c2c_ones(client, world):
    answer = listing(client)
    assert len(SKITOUR_IN_WINDOW) == 30
    assert external(answer, 'skitour') == SKITOUR_IN_WINDOW
    assert len(external(answer, 'gulliver')) == GULLIVER_LISTED
    assert {world['c2c_skiing'], world['c2c_hiking']} <= set(ids(answer))
    assert answer['total'] == len(answer['items'])
    # the day desc: the list is ordered, all the sources mixed
    days = [item['date'] for item in answer['items']]
    assert days == sorted(days, reverse=True)


def test_dates_are_shifted_to_the_days_before_today(client, db_connection, world):
    answer = listing(client)

    def days(source):
        return {i['date'] for i in answer['items'] if i['source'] == source}

    partner_days = days('skitour') | days('gulliver')
    # the newest skitour outings are of the day before the recording (the API
    # dates them at 00:00 and lists them the day after), so yesterday here;
    # gulliver has a report of the day of its recording, so today
    yesterday = TODAY - datetime.timedelta(days=1)
    assert max(days('skitour')) == yesterday.isoformat()
    assert max(days('gulliver')) == TODAY.isoformat()
    assert min(partner_days) >= (TODAY - datetime.timedelta(days=14)).isoformat()
    by_id = {item['id']: item for item in answer['items']}
    # skitour: recorded on 2026-11-25 (the epochs are Paris midnights), harvested
    # six days later
    assert by_id['skitour:188899']['date'] == '2026-11-30'
    assert by_id['skitour:188900']['date'] == '2026-11-27'
    for ext, day in SKITOUR_PARIS_DAY.items():
        assert by_id[f'skitour:{ext}']['date'] == (day + SKITOUR_SHIFT).isoformat()


def test_items_carry_credit_rating_and_areas(client, world):
    by_id = {item['id']: item for item in listing(client)['items']}
    vanoise = by_id['skitour:188891']
    assert vanoise['credit'] == {
        'site': 'skitour.fr',
        'site_url': 'https://skitour.fr',
    }
    assert vanoise['rating']['ski_rating_min'] == '2.2'
    assert vanoise['geometry']['quality'] == 'summit'
    assert [a['document_id'] for a in vanoise['areas']] == [world['vanoise']]
    assert vanoise['areas'][0]['title'] == 'Vanoise'
    # a skitour outing without summit: the start point locates it
    start = by_id['skitour:188880']
    assert start['geometry']['quality'] == 'start'
    assert [a['document_id'] for a in start['areas']] == [world['vanoise']]
    pila = by_id['gulliver:350643']
    assert pila['credit']['site'] == 'gulliver.it'
    assert pila['geometry']['quality'] == 'start'
    assert [a['document_id'] for a in pila['areas']] == [world['aosta']]
    # no coordinates: no geometry, no area, still listed; its GPX linked
    assert by_id['gulliver:350553']['geometry'] is None
    assert by_id['gulliver:350553']['areas'] == []
    assert by_id['gulliver:350553']['gpx_url'] == (
        'https://www.gulliver.it/wp-content/uploads/2026/11/2026-11-22-10-05-42.gpx'
    )
    assert by_id['skitour:188880']['gpx_url'] is None


def test_texts_are_stored_never_served(client, session, world):
    row = (
        session.query(PartnerOuting)
        .filter_by(source='gulliver', external_id='350645')
        .one()
    )
    assert row.texts['narrative'] == '[text 491 chars]'
    answer = client.get('/partner-outings', status=200)
    assert '[text ' not in answer.text
    assert all('texts' not in item for item in answer.json['items'])


def test_areas_are_assigned_by_the_point(db_connection, session, world):
    # points outside the two test areas get none, the others exactly one
    rows = {
        (r.source, r.external_id): r.area_ids
        for r in session.query(PartnerOuting).all()
    }
    for ext in SKITOUR_IN_VANOISE:
        assert rows[('skitour', ext)] == [world['vanoise']]
    for ext in GULLIVER_IN_AOSTA:
        assert rows[('gulliver', ext)] == [world['aosta']]
    # points in Lauziere or Ecrins: not in a test area
    assert rows[('skitour', '188899')] == []
    assert rows[('skitour', '188888')] == []
    assert all(
        rows[('skitour', ext)] == [] for ext in SKITOUR_IN_WINDOW - SKITOUR_IN_VANOISE
    )
    # no point at all
    assert rows[('gulliver', '350553')] == []


def test_area_filter(client, world):
    vanoise = listing(client, a=world['vanoise'])
    assert external(vanoise, 'skitour') == SKITOUR_IN_VANOISE
    assert external(vanoise, 'gulliver') == set()
    # the c2c outing of the area is merged with the partner ones
    assert world['c2c_skiing'] in ids(vanoise)
    assert world['c2c_hiking'] not in ids(vanoise)
    aosta = listing(client, a=world['aosta'])
    assert external(aosta, 'gulliver') == GULLIVER_IN_AOSTA
    assert external(aosta, 'skitour') == set()
    assert world['c2c_hiking'] in ids(aosta)


def test_other_filters(client, world):
    sources = listing(client, sources='gulliver')
    assert len(external(sources, 'gulliver')) == GULLIVER_LISTED
    assert {i['source'] for i in sources['items']} == {'gulliver'}
    assert sources['total'] == GULLIVER_LISTED

    only_c2c = listing(client, sources='c2c')
    assert {i['source'] for i in only_c2c['items']} == {'c2c'}

    snowshoeing = listing(client, act='snowshoeing')
    assert ids(snowshoeing) == ['gulliver:350602']

    hiking = listing(client, act='hiking')
    assert 'gulliver:350553' in ids(hiking)
    assert world['c2c_hiking'] in ids(hiking)
    assert not any(i.startswith('skitour:') for i in ids(hiking))

    steep = listing(client, steep='true', sources='skitour,gulliver')
    gulliver_steep = {f'gulliver:{ext}' for ext in GULLIVER_STEEP}
    assert set(ids(steep)) == {'skitour:188878', *gulliver_steep}

    # ski rating 4.1 and more: the 4.3 of skitour, the skisteep 4.1 and the two
    # OS (4.1-5.6) of gulliver
    rated = listing(client, trat='4.1,', sources='skitour,gulliver')
    assert set(ids(rated)) == {'skitour:188878', *gulliver_steep}

    # a day
    recorded_day = datetime.date(2026, 11, 24)  # Paris day of 14 of the outings
    day = (recorded_day + SKITOUR_SHIFT).isoformat()
    that_day = listing(client, date=day, sources='skitour')
    assert external(that_day, 'skitour') == {
        ext for ext, d in SKITOUR_PARIS_DAY.items() if d == recorded_day
    }
    assert len(external(that_day, 'skitour')) == 14


def test_paging_keeps_the_total(client, world):
    first = listing(client, limit=5)
    second = listing(client, limit=5, offset=5)
    assert first['total'] == second['total'] > 5
    assert not set(ids(first)) & set(ids(second))


def test_sources_are_degraded_on_purpose(client, world):
    # the real skitour recording parses completely: `ok`. Gulliver too, but its
    # cold lookup cache leaves routes for the next runs (not a failure: `ok`)
    answer = client.get('/partner-outings/sources', status=200).json
    sources = {s['source']: s for s in answer['sources']}
    # the sources switched off (harvest.partners.<name>.enabled): off by default
    off = ('bivouak', 'gipfelbuch', 'skitourenportal', 'onice')
    assert set(sources) == {'skitour', 'gulliver', *off}
    for name in off:
        assert sources[name]['status'] == 'disabled'
        assert sources[name]['status_detail'] == 'not configured'
    assert sources['skitour']['status'] == 'ok'
    assert sources['skitour']['status_detail'] is None
    assert sources['skitour']['last_fetched'] == 30
    assert sources['gulliver']['status'] == 'ok'
    assert sources['gulliver']['status_detail'] is None
    assert sources['gulliver']['last_fetched'] == GULLIVER_COUNT
    assert sources['gulliver']['last_skipped'] == {
        'duplicate': 37,
        'too_old': 2,
        'route_lookup_deferred': 90,
        'unmapped_activity:cycle': 1,
    }
    for name in ('skitour', 'gulliver'):
        assert sources[name]['last_success_at'] == NOW.isoformat()
    for source in sources.values():
        # on-ice.it answers on plain http only
        scheme = 'http://' if source['source'] == 'onice' else 'https://'
        assert source['site_url'].startswith(scheme)
    # the listing carries the same statuses
    listed = {s['source']: s['status'] for s in listing(client)['sources']}
    assert listed == {
        'skitour': 'ok',
        'gulliver': 'ok',
        'bivouak': 'disabled',
        'gipfelbuch': 'disabled',
        'skitourenportal': 'disabled',
        'onice': 'disabled',
    }


def test_health_lists_the_partners(client, world):
    response = client.get('/health', status='*')
    # the partner harvesters, as the other harvesters (degraded is no failure)
    harvest = response.json['harvest']
    for name in ('partners.skitour', 'partners.gulliver'):
        assert harvest[name]['sources'] == 1
        assert harvest[name]['failing'] == 0
        assert harvest[name]['last_success']
    assert 'partners' not in response.json


def test_second_harvest_is_idempotent(client, session, world):
    before = listing(client)
    # a later run, the same day: same rows, same answer
    job.harvest_partner_outings(SETTINGS, now=NOW + datetime.timedelta(hours=1))
    session.expire_all()
    assert session.query(PartnerOuting).count() == 30 + GULLIVER_COUNT
    # the second gulliver run asks for 2 days only: page 1 and the front page,
    # whose reports are all in the lookup cache now. The routes the first run
    # left over were not recorded: 3 failed lookups, then the others deferred
    gulliver = session.get(PartnerSource, 'gulliver')
    assert gulliver.status == 'degraded'
    assert gulliver.status_detail == '3 lookups failed'
    assert gulliver.last_requests == 1 + 1 + 3
    assert session.get(PartnerSource, 'skitour').consecutive_failures == 0
    after = listing(client)
    assert ids(after) == ids(before)
