"""The location hints end to end: the job on the real recordings of gipfelbuch,
skitourenportal and bivouak (fixture mode), with c2c areas and a few summits
named like those of the recordings.
"""

import datetime
import math
from collections import Counter

import pytest
from sqlalchemy import select

from c2corg_api.jobs import harvest_partner_outings as job
from c2corg_api.models.area import Area
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.partner_outing import PartnerOuting, PartnerSource
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.partners import region_map

UTC = datetime.UTC
NOW = datetime.datetime(2026, 11, 30, 12, 0, tzinfo=UTC)
EARTH = 6378137.0
SOURCES = ('gipfelbuch', 'skitourenportal', 'bivouak')
SETTINGS = {
    'harvest.partners.enabled': 'false',
    **{f'harvest.partners.{name}.enabled': 'true' for name in SOURCES},
    'partners.interval_minutes': '15',
    'partners.retention_days': '400',
    'partners.transport': 'fixtures',
    'partners.fixtures_dir': '',
    'partners.allow_synthetic': 'false',
}
# rough boxes: enough to tell the countries of the recordings apart
COUNTRIES = {
    'CH': (5.9, 45.8, 10.5, 47.8),
    'LI': (9.47, 47.04, 9.64, 47.27),
    'AT': (9.6, 46.4, 17.2, 49.0),
    'DE': (9.5, 47.3, 13.0, 48.5),
    'IT': (6.6, 44.0, 13.0, 46.4),
    'FR': (4.0, 43.5, 7.0, 46.4),
}
# the five Bundesländer of skitourenportal (ids of regions/skitourenportal.json)
STATES = {
    'Salzburg': (12.1, 46.9, 13.9, 48.0),
    'Oberösterreich': (13.0, 47.5, 14.9, 48.8),
    'Niederösterreich': (14.5, 47.4, 17.0, 49.0),
    'Kärnten': (12.6, 46.4, 15.0, 47.1),
    'Steiermark': (13.6, 46.6, 16.1, 47.8),
}
# summits named as in the recordings (name, elevation, lon, lat)
SUMMITS = [
    ('Hochgrat', 1834, 10.08, 47.49),  # gipfelbuch "Hochgrat (1834m)", D - Allgäu
    ('Pilatus', 2128, 8.25, 46.98),  # "Pilatus (2118m)": 10 m apart
    ('Piz Corvatsch', 3451, 9.82, 46.41),
    ('Naafkopf', 2570, 9.55, 47.08),  # in Liechtenstein, on the border
    ('Le Dôme', 3016, 7.2, 46.33),
    ('Mattjischhorn', 2461, 9.72, 46.83),  # "Mattjisch Horn"
    ('Hoher Sonnblick', 3106, 12.96, 47.05),
    ('Moschkogel', 1916, 13.9, 46.7),
    # an altitude far off: not "Kronberg (1663m)"
    ('Kronberg', 1900, 9.32, 47.29),
    # ambiguous: two Spitzstein near 1598 m
    ('Spitzstein', 1598, 12.2, 47.66),
    ('Spitzstein', 1620, 12.0, 47.6),
]


def mercator(lon, lat):
    return (
        EARTH * math.radians(lon),
        EARTH * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)),
    )


def box(lon0, lat0, lon1, lat1):
    x0, y0 = mercator(lon0, lat0)
    x1, y1 = mercator(lon1, lat1)
    return f'SRID=3857;POLYGON(({x0} {y0},{x0} {y1},{x1} {y1},{x1} {y0},{x0} {y0}))'


def make_world(session):
    for code, bounds in COUNTRIES.items():
        area = Area(
            document_id=region_map.country_area(code),
            area_type='country',
            locales=[DocumentLocale(lang='en', title=code)],
        )
        area.geometry = DocumentGeometry(geom_detail=box(*bounds))
        session.add(area)
    for name, bounds in STATES.items():
        area = Area(
            document_id=region_map.lookup('skitourenportal', name).area_ids[0],
            area_type='admin_limits',
            locales=[DocumentLocale(lang='de', title=name)],
        )
        area.geometry = DocumentGeometry(geom_detail=box(*bounds))
        session.add(area)
    for name, elevation, lon, lat in SUMMITS:
        x, y = mercator(lon, lat)
        session.add(
            Waypoint(
                waypoint_type='summit',
                elevation=elevation,
                locales=[WaypointLocale(lang='de', title=name)],
                geometry=DocumentGeometry(geom=f'SRID=3857;POINT({x} {y})'),
            )
        )
    session.commit()


@pytest.fixture
def world(session, monkeypatch):
    """The harvest of every outing of the recordings."""
    # not the 14 days of a first run: the older outings have more hints
    monkeypatch.setattr(job, 'INITIAL_DAYS', 365)
    make_world(session)
    job.harvest_partner_outings(SETTINGS, now=NOW)
    session.expire_all()


@pytest.fixture
def demo(session):
    """The harvest of the local demo: the first run, 14 days."""
    make_world(session)
    job.harvest_partner_outings(SETTINGS, now=NOW)
    session.expire_all()


def stored(session, source):
    return {
        r.external_id: r
        for r in session.scalars(
            select(PartnerOuting).where(PartnerOuting.source == source)
        )
    }


def qualities(session, source):
    return Counter(r.geom_quality for r in stored(session, source).values())


@pytest.mark.parametrize('harvest', ['demo', 'world'])
def test_no_source_is_down(session, harvest, request):
    request.getfixturevalue(harvest)
    for name in SOURCES:
        row = session.get(PartnerSource, name)
        assert row.status in ('ok', 'degraded'), (name, row.status_detail)
        assert row.last_upserted > 0


def test_a_detail_page_never_recorded_fails_its_outing_only(session, demo):
    # the 14 days of the demo ask bivouak for a detail page that was never
    # recorded ("no fixture": down): that outing keeps its hints, the run goes on
    bivouak = session.get(PartnerSource, 'bivouak')
    assert bivouak.status == 'degraded'
    assert bivouak.status_detail == '1 lookups failed'
    assert bivouak.last_skipped['lookup_failed'] == 1
    assert bivouak.consecutive_failures == 0


def test_gipfelbuch_summits_are_matched(session, world):
    rows = stored(session, 'gipfelbuch')
    by_summit = {}
    for row in rows.values():
        by_summit.setdefault(row.title, row)

    def quality(title):
        return next(r.geom_quality for t, r in by_summit.items() if t.startswith(title))

    assert quality('Hochgrat') == 'summit_match'
    assert quality('Pilatus') == 'summit_match'
    assert quality('Piz Corvatsch') == 'summit_match'
    assert quality('Naafkopf') == 'summit_match'
    assert quality('Le Dôme') == 'summit_match'
    assert quality('Mattjisch Horn') == 'summit_match'
    assert quality('Kronberg') == 'none'  # 237 m apart
    assert quality('Spitzstein') == 'none'  # two candidates
    # the points the partner gave stay theirs
    counts = qualities(session, 'gipfelbuch')
    assert counts['summit'] >= 15
    assert counts['summit_match'] == 8  # Pilatus and Piz Corvatsch twice
    # the others: their country (when the report names one), no point
    for row in rows.values():
        if row.geom_quality == 'none':
            assert row.geom is None
            assert len(row.area_ids) == (1 if row.region else 0), row.title
        else:
            assert row.area_ids, row.title


def test_skitourenportal_summits_regions_and_markers(session, world):
    rows = stored(session, 'skitourenportal')
    counts = qualities(session, 'skitourenportal')
    # a marker on the map; else the summit of the title; else the Bundesland
    assert counts['route'] == 25
    # Hoher Sonnblick ("Hoher Sonnblick 3.106m"), Moschkogel (5 reports)
    assert counts['summit_match'] == 6
    assert counts['none'] == 0
    assert counts['area_centroid'] == len(rows) - 25 - 6
    sonnblick = next(r for r in rows.values() if r.title.startswith('Hoher Sonnb'))
    assert sonnblick.geom_quality == 'summit_match'
    # not a c2c summit: the centroid of its Bundesland
    kreuzkogel = next(r for r in rows.values() if r.title == 'Kreuzkogel 2686m')
    assert kreuzkogel.geom_quality == 'area_centroid'
    austria = region_map.country_area('AT')
    for row in rows.values():
        if row.geom_quality == 'area_centroid':
            region = region_map.lookup('skitourenportal', row.region)
            assert row.area_ids == sorted([*region.area_ids, austria])


def test_a_second_harvest_uses_the_cached_resolutions(session, world):
    before = {
        (r.source, r.external_id): (r.geom_quality, r.area_ids)
        for s in SOURCES
        for r in stored(session, s).values()
    }
    # the summits are gone, the cached resolutions are not
    for waypoint in session.scalars(select(Waypoint)):
        session.delete(waypoint.geometry)
    session.commit()
    job.harvest_partner_outings(SETTINGS, now=NOW + datetime.timedelta(hours=1))
    session.expire_all()
    after = {
        (r.source, r.external_id): (r.geom_quality, r.area_ids)
        for s in SOURCES
        for r in stored(session, s).values()
    }
    assert after == before
