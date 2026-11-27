"""Locating the partner outings without coordinates (`jobs.partner_locations`)."""

import datetime
import math
from collections import Counter

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from c2corg_api.jobs import harvest_partner_outings as job
from c2corg_api.jobs import partner_locations as locations
from c2corg_api.models.area import Area
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.partner_outing import PartnerOuting, PartnerSource
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.partners.lookups import MemoryLookupCache
from c2corg_api.partners.model import FetchResult, HarvestedOuting, RateLimit

UTC = datetime.UTC
NOW = datetime.datetime(2026, 11, 25, 12, 0, tzinfo=UTC)
EARTH = 6378137.0
# the ids of partners/regions/countries.json and skitourenportal.json
SWITZERLAND = 14067
AUSTRIA = 14257
SALZBURG = 282687
# partners/regions/onice.json and gulliver.json
ITALY = 14270
AOSTA = 280072
TORINO = 280066
CUNEO = 280000
SETTINGS = {
    # not the default (empty: kept forever): a retention, to test the purge
    'partners.retention_days': '31',
    'partners.transport': 'http',
}


def mercator(lon, lat):
    return (
        EARTH * math.radians(lon),
        EARTH * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)),
    )


def box(lon0, lat0, lon1, lat1):
    x0, y0 = mercator(lon0, lat0)
    x1, y1 = mercator(lon1, lat1)
    return f'SRID=3857;POLYGON(({x0} {y0},{x0} {y1},{x1} {y1},{x1} {y0},{x0} {y0}))'


@pytest.fixture
def db(db_connection):
    with Session(db_connection, join_transaction_mode='create_savepoint') as session:
        yield session


def make_area(db, document_id, area_type, geom, title='Area'):
    area = Area(
        document_id=document_id,
        area_type=area_type,
        locales=[DocumentLocale(lang='en', title=title)],
    )
    area.geometry = DocumentGeometry(geom_detail=geom)
    db.add(area)
    db.flush()
    return area


def make_waypoint(db, titles, elevation, lon, lat, waypoint_type='summit'):
    x, y = mercator(lon, lat)
    waypoint = Waypoint(
        waypoint_type=waypoint_type,
        elevation=elevation,
        locales=[
            WaypointLocale(lang=lang, title=title) for lang, title in titles.items()
        ],
        geometry=DocumentGeometry(geom=f'SRID=3857;POINT({x} {y})'),
    )
    db.add(waypoint)
    db.flush()
    return waypoint.document_id


@pytest.fixture
def world(db):
    """Switzerland and Austria as boxes, Salzburg in Austria, a few summits."""
    make_area(db, SWITZERLAND, 'country', box(6.0, 45.8, 10.0, 47.0), 'Switzerland')
    make_area(db, AUSTRIA, 'country', box(10.0, 46.5, 17.0, 49.0), 'Austria')
    make_area(db, SALZBURG, 'admin_limits', box(12.0, 47.0, 14.0, 48.0), 'Salzburg')
    ids = {
        'palu': make_waypoint(
            db, {'de': 'Piz Palü', 'it': 'Pizzo Palù / Piz Palü'}, 3900, 9.95, 46.38
        ),
        'galise': make_waypoint(db, {'fr': 'Pointe de la Galise'}, 3343, 7.05, 45.95),
        # two summits named alike, in Austria
        'hochgrat_a': make_waypoint(db, {'de': 'Hochgrat'}, 1834, 12.5, 47.5),
        'hochgrat_b': make_waypoint(db, {'de': 'Hochgrat'}, 2100, 13.5, 47.5),
        'sonnblick': make_waypoint(db, {'de': 'Hoher Sonnblick'}, 3106, 12.96, 47.05),
        'forclette': make_waypoint(
            db, {'fr': 'Col de la Forclette'}, 2869, 7.6, 46.1, waypoint_type='pass'
        ),
        'hut': make_waypoint(
            db, {'de': 'Bergli Hütte'}, 3299, 8.0, 46.5, waypoint_type='hut'
        ),
    }
    gone = make_waypoint(db, {'de': 'Weggezogen'}, 2000, 8.0, 46.5)
    redirect = db.get(Waypoint, gone)
    redirect.redirects_to = ids['palu']
    db.flush()
    return ids


def outing(external_id='1', source='gipfelbuch', **kwargs):
    values = {
        'source': source,
        'external_id': external_id,
        'url': f'https://example.org/{external_id}',
        'title': 'Tour',
        'date': NOW.date(),
        'activities': ('skitouring',),
    }
    return HarvestedOuting(**{**values, **kwargs})


def resolve(db, *outings, lookups=None):
    lookups = lookups if lookups is not None else MemoryLookupCache()
    located, area_ids, counts = locations.resolve_locations(db, lookups, list(outings))
    return {o.external_id: o for o in located}, area_ids, counts


def place_of(db, waypoint_id):
    x, y = db.execute(
        select(
            func.ST_X(func.ST_Transform(DocumentGeometry.geom, 4326)),
            func.ST_Y(func.ST_Transform(DocumentGeometry.geom, 4326)),
        ).where(DocumentGeometry.document_id == waypoint_id)
    ).one()
    return pytest.approx(x), pytest.approx(y)


# ------------------------------------------------------------------- summits


def test_summit_by_name_without_accents(db, world):
    located, area_ids, counts = resolve(
        db, outing(summit_name='Piz Palu', elevation_max=3905, country='CH')
    )
    o = located['1']
    assert o.geom_quality == 'summit_match'
    assert (o.lon, o.lat) == place_of(db, world['palu'])
    assert area_ids == {}  # from the point, by assign_areas
    assert counts == Counter(summit_match=1)


def test_summit_by_another_locale_and_part_of_the_title(db, world):
    located, _, _ = resolve(db, outing(summit_name='Pizzo Palù', elevation_max=3890))
    assert located['1'].geom_quality == 'summit_match'


def test_altitude_mismatch(db, world):
    located, _, counts = resolve(db, outing(summit_name='Piz Palü', elevation_max=3700))
    assert (located['1'].lat, located['1'].geom_quality) == (None, 'none')
    assert counts == Counter(unresolved=1)
    # within 50 m
    located, _, _ = resolve(db, outing(summit_name='Piz Palü', elevation_max=3850))
    assert located['1'].geom_quality == 'summit_match'


def test_ambiguous_names(db, world):
    located, _, counts = resolve(db, outing(summit_name='Hochgrat'))
    assert located['1'].geom_quality == 'none'
    assert counts == Counter(unresolved=1)
    # the altitude tells them apart
    located, _, _ = resolve(db, outing(summit_name='Hochgrat', elevation_max=2080))
    assert (located['1'].lon, located['1'].lat) == place_of(db, world['hochgrat_b'])


def test_generic_words_only_with_an_altitude(db, world):
    located, _, _ = resolve(db, outing(summit_name='Galise', elevation_max=3340))
    assert (located['1'].lon, located['1'].lat) == place_of(db, world['galise'])
    # "Galise" alone could be anything called so
    located, _, _ = resolve(db, outing(summit_name='Galise'))
    assert located['1'].geom_quality == 'none'
    # the full name needs none
    located, _, _ = resolve(db, outing(summit_name='Pointe de la Galise'))
    assert located['1'].geom_quality == 'summit_match'


def test_umlauts_spelled_out(db, world):
    located, _, _ = resolve(
        db, outing(summit_name='Hoher Sonnblick', elevation_max=3106, country='AT')
    )
    assert located['1'].geom_quality == 'summit_match'
    located, _, _ = resolve(db, outing(summit_name='PIZ PALUE', elevation_max=3899))
    assert located['1'].geom_quality == 'summit_match'


def test_restricted_to_the_country(db, world):
    located, _, _ = resolve(
        db, outing(summit_name='Piz Palü', elevation_max=3900, country='AT')
    )
    assert located['1'].geom_quality == 'none'
    # an unknown country restricts nothing
    located, _, _ = resolve(
        db, outing(summit_name='Piz Palü', elevation_max=3900, country='ZZ')
    )
    assert located['1'].geom_quality == 'summit_match'


def test_passes_but_not_huts_nor_redirected_waypoints(db, world):
    located, _, _ = resolve(
        db,
        outing('pass', summit_name='Col de la Forclette', elevation_max=2869),
        outing('hut', summit_name='Bergli Hütte', elevation_max=3299),
        outing('redirected', summit_name='Weggezogen', elevation_max=2000),
    )
    assert located['pass'].geom_quality == 'summit_match'
    assert located['hut'].geom_quality == 'none'
    assert located['redirected'].geom_quality == 'none'


def test_outings_with_a_position_are_kept(db, world):
    given = outing(
        summit_name='Piz Palü', lon=9.9, lat=46.4, geom_quality='summit', region='X'
    )
    located, area_ids, counts = resolve(db, given)
    assert located['1'] == given
    assert (area_ids, counts) == ({}, Counter())


def test_resolutions_are_cached(db, world):
    lookups = MemoryLookupCache()
    hinted = outing(summit_name='Piz Palü', elevation_max=3900, country='CH')
    missing = outing('2', summit_name='Nowhere Peak', elevation_max=2000)
    resolve(db, hinted, missing, lookups=lookups)
    assert (
        lookups.get('resolve:summit:piz palu|3900|CH')['waypoint_id'] == world['palu']
    )
    assert lookups.get('resolve:summit:nowhere peak|2000|') == {'waypoint_id': None}
    # the next run asks the cache only
    db.get(Waypoint, world['palu']).redirects_to = world['galise']
    db.flush()
    located, _, _ = resolve(db, hinted, missing, lookups=lookups)
    assert located['1'].geom_quality == 'summit_match'
    assert located['2'].geom_quality == 'none'


def test_long_names_fit_the_lookup_key():
    hint = locations._Hint('x' * 300, 'x', 2000, None, 'CH')
    assert len(hint.cache_key) <= 128
    assert hint.cache_key != locations._Hint('x' * 299, 'x', 2000, None, 'CH').cache_key


# ------------------------------------------------------- regions, countries


def test_region_centroid_and_its_areas(db, world):
    located, area_ids, counts = resolve(
        db,
        outing(source='skitourenportal', region='Salzburg', country='AT'),
        # an unknown summit: the region still places it
        outing('2', source='skitourenportal', region='Salzburg', summit_name='Nix'),
    )
    o = located['1']
    assert o.geom_quality == 'area_centroid'
    assert (o.lon, o.lat) == (pytest.approx(13.0), pytest.approx(47.5, abs=0.01))
    assert area_ids[('skitourenportal', '1')] == [AUSTRIA, SALZBURG]
    assert located['2'].geom_quality == 'area_centroid'
    assert counts == Counter(area_centroid=2)


def test_region_text_is_folded(db, world):
    located, _, _ = resolve(db, outing(source='skitourenportal', region='SALZBURG '))
    assert located['1'].geom_quality == 'area_centroid'


def test_unknown_region_falls_back_to_the_country(db, world):
    located, area_ids, counts = resolve(
        db, outing(source='skitourenportal', region='Tirol', country='AT')
    )
    assert (located['1'].lat, located['1'].geom_quality) == (None, 'none')
    assert area_ids == {('skitourenportal', '1'): [AUSTRIA]}
    assert counts == Counter(country=1)


def test_country_only(db, world):
    located, area_ids, _ = resolve(
        db, outing(region='CH - Zentralschweiz', country='CH', summit_name='Nix')
    )
    assert located['1'].geom_quality == 'none'
    assert area_ids == {('gipfelbuch', '1'): [SWITZERLAND]}


def test_nothing_known(db, world):
    _, area_ids, counts = resolve(db, outing(region='Atlantis', country='ZZ'))
    assert (area_ids, counts) == ({}, Counter(unresolved=1))


def test_region_area_without_geometry_falls_back_to_the_country(db):
    # the database has no area for Salzburg (another database, a deleted area)
    located, area_ids, _ = resolve(
        db, outing(source='skitourenportal', region='Salzburg', country='AT')
    )
    assert located['1'].geom_quality == 'none'
    assert area_ids == {('skitourenportal', '1'): [AUSTRIA]}


@pytest.fixture
def italy(db):
    make_area(db, SWITZERLAND, 'country', box(6.0, 45.8, 10.0, 47.0), 'Switzerland')
    make_area(db, ITALY, 'country', box(6.6, 37.0, 18.5, 47.0), 'Italy')
    make_area(db, AOSTA, 'admin_limits', box(6.8, 45.5, 7.9, 46.0), "Valle d'Aosta")
    make_area(db, TORINO, 'admin_limits', box(6.6, 44.8, 8.0, 45.5), 'Torino')
    make_area(db, CUNEO, 'admin_limits', box(6.8, 44.0, 8.2, 44.8), 'Cuneo')


def test_onice_italian_region(db, italy):
    located, area_ids, counts = resolve(
        db,
        outing(source='onice', region="Valle d'Aosta", country='IT', summit_name='Nix'),
        outing('2', source='onice', region='Svizzera', country='CH'),
        outing('3', source='onice', region='Altro'),
    )
    o = located['1']
    assert o.geom_quality == 'area_centroid'
    assert (o.lon, o.lat) == (pytest.approx(7.35), pytest.approx(45.75, abs=0.01))
    assert sorted(area_ids[('onice', '1')]) == [ITALY, AOSTA]
    # a country in Italian: the country only
    assert located['2'].geom_quality == 'none'
    assert area_ids[('onice', '2')] == [SWITZERLAND]
    assert ('onice', '3') not in area_ids
    assert counts == Counter(area_centroid=1, country=1, unresolved=1)


def test_onice_region_of_several_provinces(db, italy):
    located, area_ids, _ = resolve(
        db, outing(source='onice', region='Piemonte', country='IT')
    )
    # the centroid of the first province, the areas of all those in the database
    assert located['1'].geom_quality == 'area_centroid'
    assert located['1'].lon == pytest.approx(7.3)
    assert {TORINO, CUNEO, ITALY} <= set(area_ids[('onice', '1')])


def test_gulliver_province_code(db, italy):
    located, area_ids, counts = resolve(
        db,
        outing(source='gulliver', region='Piemonte - CN', country='IT'),
        outing('2', source='gulliver', region='Valais (CH) - Brig', country='CH'),
    )
    o = located['1']
    assert o.geom_quality == 'area_centroid'
    assert (o.lon, o.lat) == (pytest.approx(7.5), pytest.approx(44.4, abs=0.01))
    assert sorted(area_ids[('gulliver', '1')]) == [ITALY, CUNEO]
    assert located['2'].geom_quality == 'none'
    assert area_ids[('gulliver', '2')] == [SWITZERLAND]
    assert counts == Counter(area_centroid=1, country=1)


# ----------------------------------------------------------------- the job


class FakeTransport:
    request_count = 1


def run_fake(db, outings, skipped=None):
    class Fake:
        name = 'gipfelbuch'
        site_name = 'gipfelbuch.example'
        site_url = 'https://gipfelbuch.example'
        required_secrets = ()
        rate = RateLimit(0, 10, 5)

        def fetch(self, ctx):
            return FetchResult(outings=list(outings), skipped=Counter(skipped or {}))

    return job.run_source(
        db, Fake(), FakeTransport(), MemoryLookupCache(), NOW, SETTINGS
    )


def rows(db):
    db.expire_all()
    return {
        r.external_id: r
        for r in db.scalars(
            select(PartnerOuting).where(PartnerOuting.source == 'gipfelbuch')
        )
    }


def test_the_job_stores_the_located_outings(db, world):
    status = run_fake(
        db,
        [
            outing('summit', summit_name='Piz Palü', elevation_max=3900, country='CH'),
            outing('region', source='gipfelbuch', region='Salzburg', country='AT'),
            outing('none'),
        ],
    )
    assert status == 'ok'
    stored = rows(db)
    assert stored['summit'].geom_quality == 'summit_match'
    assert stored['summit'].geom is not None
    # the areas of the point
    assert stored['summit'].area_ids == [SWITZERLAND]
    # no region table for gipfelbuch: the country only
    assert (stored['region'].geom, stored['region'].area_ids) == (None, [AUSTRIA])
    assert (stored['none'].geom_quality, stored['none'].area_ids) == ('none', [])


def test_area_centroids_keep_the_areas_of_their_region(db, world):
    class Fake:
        name = 'skitourenportal'
        site_name = 'skitourenportal.example'
        site_url = 'https://skitourenportal.example'
        required_secrets = ()
        rate = RateLimit(0, 10, 5)

        def fetch(self, ctx):
            return FetchResult(
                outings=[outing(source='skitourenportal', region='Salzburg')]
            )

    job.run_source(db, Fake(), FakeTransport(), MemoryLookupCache(), NOW, SETTINGS)
    # the purge recomputes the areas of every outing with a point
    job.assign_areas(db)
    db.expire_all()
    row = db.scalars(
        select(PartnerOuting).where(PartnerOuting.source == 'skitourenportal')
    ).one()
    assert row.geom_quality == 'area_centroid'
    assert row.area_ids == [AUSTRIA, SALZBURG]


def test_failed_lookups_make_the_run_degraded(db, world):
    status = run_fake(db, [outing()], skipped={'lookup_failed': 2})
    assert status == 'degraded'
    source = db.get(PartnerSource, 'gipfelbuch')
    assert source.status_detail == '2 lookups failed'
    assert source.last_skipped == {'lookup_failed': 2}
    assert source.consecutive_failures == 0
    assert len(rows(db)) == 1


@pytest.mark.parametrize(
    ('source', 'region', 'areas'),
    [
        ('onice', "Valle d'Aosta", [ITALY, AOSTA]),
        ('gulliver', 'Piemonte - CN', [ITALY, CUNEO]),
    ],
)
def test_the_job_stores_italian_regions(db, italy, source, region, areas):
    class Fake:
        name = source
        site_name = f'{source}.example'
        site_url = f'https://{source}.example'
        required_secrets = ()
        rate = RateLimit(0, 10, 5)

        def fetch(self, ctx):
            return FetchResult(
                outings=[outing(source=source, region=region, country='IT')]
            )

    job.run_source(db, Fake(), FakeTransport(), MemoryLookupCache(), NOW, SETTINGS)
    job.assign_areas(db)
    db.expire_all()
    row = db.scalars(select(PartnerOuting).where(PartnerOuting.source == source)).one()
    assert row.geom_quality == 'area_centroid'
    assert row.geom is not None
    assert row.area_ids == areas
