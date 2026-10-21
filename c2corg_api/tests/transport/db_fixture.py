"""Test data for the tests using the database."""
from geoalchemy2.shape import from_shape
from pyproj import Transformer
from shapely.geometry import Point

from c2corg_api.models.stoparea import Stoparea
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.models.waypoint_stoparea import WaypointStoparea
from c2corg_api.tests.transport.gtfs_fixture import TODAY, gtfs_archive
from c2corg_api.transport import gtfs, importer

FEED = {
    'id': 'test',
    'name': 'Test feed',
    'url': 'https://example.org/gtfs.zip',
    'license': 'Licence Ouverte 2.0',
    'attribution': 'Test attribution',
}

_to_3857 = Transformer.from_crs(4326, 3857, always_xy=True).transform

# the stops of the GTFS fixture are around (6.0, 45.0)
WORLD = '-100000,-100000,10000000,10000000'


def import_test_feed(session, **overrides):
    """Imports the GTFS fixture as the feed `test`."""
    importer.save(
        session, FEED, gtfs.parse(gtfs_archive(**overrides), TODAY),
        'checksum')
    session.flush()


def navitia_stoparea(session, stoparea_id, navitia_id, name, line, lon, lat):
    session.add(Stoparea(
        stoparea_id=stoparea_id,
        navitia_id=navitia_id,
        stoparea_name=name,
        line=line,
        operator='Operator',
        geom=from_shape(Point(*_to_3857(lon, lat)), srid=3857)))


def add_navitia_stops(session):
    """
    Navitia stops around the GTFS stops of the fixture, and a waypoint they
    are associated with:
    - 'nav-mairie' ends with the id of the GTFS stop S2: linked by its id
    - 'nav-col' has the line code of the line serving S3 and is 20 m from
      it: linked by its line and its distance
    - 'nav-gare' is 20 m from the S1 stop but with another line code: not
      linked
    - 'nav-far' is far from every GTFS stop: not linked
    Returns the waypoint.
    """
    waypoint = Waypoint(waypoint_type='access', elevation=1000)
    waypoint.locales.append(WaypointLocale(lang='fr', title='Parking du Lac'))
    waypoint.locales.append(WaypointLocale(lang='en', title='Lake car park'))
    session.add(waypoint)
    session.flush()

    navitia_stoparea(session, 1, 'stop_area:R:Navitia:S2', 'Mairie (Ville)',
                     'Bus 1 - Gare - Col', 6.0100, 45.0100)
    navitia_stoparea(session, 2, 'stop_area:Q:99', 'Col (Ville)',
                     'Bus 1 - Gare - Col', 6.0202, 45.0200)
    navitia_stoparea(session, 3, 'stop_area:Q:98', 'Gare (Ville)',
                     'Bus 9 - Autre ligne', 6.0002, 45.0000)
    navitia_stoparea(session, 4, 'stop_area:Q:97', 'Ailleurs (Ville)',
                     'Bus 1 - Gare - Col', 7.0, 46.0)
    session.flush()

    for waypoint_stoparea_id, stoparea_id, distance in (
            (1, 1, 1.5), (2, 2, 0.5), (3, 4, 2.5)):
        session.add(WaypointStoparea(
            waypoint_stoparea_id=waypoint_stoparea_id,
            waypoint_id=waypoint.document_id,
            stoparea_id=stoparea_id,
            distance=distance))
    session.flush()
    return waypoint
