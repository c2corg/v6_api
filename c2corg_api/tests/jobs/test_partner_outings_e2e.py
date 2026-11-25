"""The vertical slice, offline: the harvest job on the recorded fixtures with
the real skitour and gulliver adapters, then `GET /partner-outings`.

This is the local demo (docs/partner-outings.md) run as a test: no network, the
fixtures of c2corg_api/tests/partners/fixtures, test areas around the places of
the fixtures, and a few c2c outings next to the partner ones.
"""

import datetime
import math

import pytest

from c2corg_api.jobs import harvest_partner_outings as job
from c2corg_api.models.area import Area
from c2corg_api.models.area_association import AreaAssociation
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.outing import Outing, OutingLocale
from c2corg_api.models.partner_outing import PartnerOuting, PartnerSource

UTC = datetime.UTC
# the fixtures were recorded on 2026-11-24: harvesting a week later shifts the
# dates of the outings by 7 days, as the demo does every day
RECORDED = datetime.date(2026, 11, 24)
NOW = datetime.datetime(2026, 12, 1, 12, 0, tzinfo=UTC)
TODAY = NOW.date()
SHIFT = TODAY - RECORDED
EARTH = 6378137.0

SETTINGS = {
    'harvest.partners.enabled': 'false',
    'harvest.partners.skitour.enabled': 'true',
    'harvest.partners.gulliver.enabled': 'true',
    'partners.interval_minutes': '15',
    'partners.retention_days': '31',
    'partners.transport': 'fixtures',
    'partners.fixtures_dir': '',
    'partners.allow_synthetic': 'true',
}

# what the fixtures hold, by external id (lon, lat of the point; date as
# recorded; ski rating min) - see c2corg_api/tests/partners/fixtures
SKITOUR_WITH_POINT = {'112345', '112346', '112348', '112351', '112352', '112355'}
SKITOUR_IN_VANOISE = {'112345', '112348', '112351'}
SKITOUR_IN_WINDOW = SKITOUR_WITH_POINT | {'112347', '112349', '112350'}
GULLIVER_WITH_POINT = {'48181', '48188', '48190', '48199', '48204', '48207', '48213'}
GULLIVER_IN_AOSTA = {'48181', '48190', '48199', '48204', '48207', '48213'}
GULLIVER_ALL = GULLIVER_WITH_POINT | {'48196', '48210'}


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
    vanoise = make_area(session, 'Vanoise', box(6.7, 45.3, 7.0, 45.5))
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
    assert external(answer, 'skitour') == SKITOUR_IN_WINDOW
    assert external(answer, 'gulliver') == GULLIVER_ALL
    assert {world['c2c_skiing'], world['c2c_hiking']} <= set(ids(answer))
    assert answer['total'] == len(answer['items'])
    # the day desc: the list is ordered, all the sources mixed
    days = [item['date'] for item in answer['items']]
    assert days == sorted(days, reverse=True)
    # the oldest fixture outing (2026-11-10) is out of the window, not purged
    assert 'skitour:112210' not in ids(answer)


def test_dates_are_shifted_to_the_days_before_today(client, db_connection, world):
    answer = listing(client)
    partner_days = {item['date'] for item in answer['items'] if item['source'] != 'c2c'}
    assert max(partner_days) == TODAY.isoformat()
    assert min(partner_days) >= (TODAY - datetime.timedelta(days=14)).isoformat()
    by_id = {item['id']: item for item in answer['items']}
    # recorded on 2026-11-24, harvested a week later
    assert by_id['skitour:112349']['date'] == '2026-12-01'
    assert (
        by_id['skitour:112345']['date']
        == (datetime.date(2026, 11, 23) + SHIFT).isoformat()
    )


def test_items_carry_credit_rating_and_areas(client, world):
    by_id = {item['id']: item for item in listing(client)['items']}
    sana = by_id['skitour:112345']
    assert sana['credit'] == {'site': 'skitour.fr', 'site_url': 'https://skitour.fr'}
    assert sana['rating']['ski_rating_min'] == '3.2'
    assert sana['geometry']['quality'] == 'summit'
    assert [a['document_id'] for a in sana['areas']] == [world['vanoise']]
    assert sana['areas'][0]['title'] == 'Vanoise'
    cheneil = by_id['gulliver:48213']
    assert cheneil['credit']['site'] == 'gulliver.it'
    assert cheneil['geometry']['quality'] == 'start'
    assert [a['document_id'] for a in cheneil['areas']] == [world['aosta']]
    # no coordinates: no geometry, no area, still listed
    assert by_id['skitour:112349']['geometry'] is None
    assert by_id['skitour:112349']['areas'] == []


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
    # a point in the Vercors and one in Ecrins: not in a test area
    assert rows[('skitour', '112355')] == []
    assert rows[('skitour', '112346')] == []
    # no point at all
    assert rows[('skitour', '112349')] == []
    assert rows[('gulliver', '48210')] == []


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
    assert external(sources, 'gulliver') == GULLIVER_ALL
    assert {i['source'] for i in sources['items']} == {'gulliver'}
    assert sources['total'] == len(GULLIVER_ALL)

    only_c2c = listing(client, sources='c2c')
    assert {i['source'] for i in only_c2c['items']} == {'c2c'}

    snowshoeing = listing(client, act='snowshoeing')
    assert ids(snowshoeing) == ['gulliver:48204']

    hiking = listing(client, act='hiking')
    assert 'gulliver:48190' in ids(hiking)
    assert world['c2c_hiking'] in ids(hiking)
    assert not any(i.startswith('skitour:') for i in ids(hiking))

    steep = listing(client, steep='true', sources='skitour,gulliver')
    assert set(ids(steep)) == {'skitour:112346', 'gulliver:48207'}

    # ski rating 4.1 and more: the couloir of skitour and the canalone of gulliver
    rated = listing(client, trat='4.1,', sources='skitour,gulliver')
    assert set(ids(rated)) == {'skitour:112346', 'gulliver:48207'}

    # a day
    day = (datetime.date(2026, 11, 24) + SHIFT).isoformat()
    that_day = listing(client, date=day, sources='skitour')
    assert external(that_day, 'skitour') == {'112349', '112351', '112352'}


def test_paging_keeps_the_total(client, world):
    first = listing(client, limit=5)
    second = listing(client, limit=5, offset=5)
    assert first['total'] == second['total'] > 5
    assert not set(ids(first)) & set(ids(second))


def test_sources_are_degraded_on_purpose(client, world):
    # each fixture set has an item that does not parse: the run is `degraded`
    answer = client.get('/partner-outings/sources', status=200).json
    sources = {s['source']: s for s in answer['sources']}
    assert set(sources) == {'skitour', 'gulliver'}
    assert sources['skitour']['status'] == 'degraded'
    assert sources['skitour']['status_detail'] == '2 items failed to parse'
    assert sources['skitour']['last_fetched'] == 10
    assert sources['gulliver']['status'] == 'degraded'
    assert sources['gulliver']['status_detail'] == '1 items failed to parse'
    assert sources['gulliver']['last_fetched'] == 9
    assert sources['gulliver']['last_skipped'] == {
        'too_old': 1,
        'route_lookup_deferred': 1,
        'unmapped_activity:kayak': 1,
    }
    for source in sources.values():
        assert source['last_success_at'] == NOW.isoformat()
        assert source['site_url'].startswith('https://')
    # the listing carries the same statuses
    listed = {s['source']: s['status'] for s in listing(client)['sources']}
    assert listed == {'skitour': 'degraded', 'gulliver': 'degraded'}


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
    assert session.query(PartnerOuting).count() == 19
    assert session.get(PartnerSource, 'skitour').consecutive_failures == 0
    after = listing(client)
    assert ids(after) == ids(before)
