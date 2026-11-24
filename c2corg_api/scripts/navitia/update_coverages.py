"""Load the coverages of Navitia (its regions of France) into the database.

To run again when Navitia changes its coverages. The rows are replaced in one
transaction, and only if every coverage could be read.
"""

import argparse
import logging
import os
import sys

import requests
from geoalchemy2.shape import from_shape
from shapely import wkt
from shapely.geometry import MultiPolygon, Polygon
from sqlalchemy import engine_from_config, func

from c2corg_api.config import get_appsettings, setup_logging
from c2corg_api.models import DBSession, commit_or_rollback
from c2corg_api.models.common.attributes import coverage_types
from c2corg_api.models.coverage import NavitiaCoverage
from c2corg_api.views.navitia import BASE_URL

log = logging.getLogger(__name__)

SRID = 4326
TIMEOUT = 60


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description='Load the coverages of Navitia into the database '
        '(NAVITIA_API_KEY in the environment).'
    )
    parser.add_argument('config_uri', help='the settings, e.g. production.ini')
    parser.add_argument(
        '--dry-run', action='store_true', help='read the coverages, save nothing'
    )
    return parser.parse_args(argv[1:])


def main(argv=sys.argv):
    args = parse_args(argv)
    setup_logging(args.config_uri)
    api_key = os.getenv('NAVITIA_API_KEY')
    if not api_key:
        sys.exit('NAVITIA_API_KEY is not set')
    shapes = {name: fetch_shape(name, api_key) for name in coverage_types}
    for name, shape in shapes.items():
        print(f'{name}: {len(shape.geoms)} polygon(s), bounds {shape.bounds}')
    if args.dry_run:
        print('Dry run: nothing saved')
        return
    settings = get_appsettings(args.config_uri)
    DBSession.configure(bind=engine_from_config(settings, 'sqlalchemy.'))
    save(shapes)
    print(f'{len(shapes)} coverages saved')


def fetch_shape(name, api_key):
    """Return the shape of a coverage, as given by Navitia."""
    response = requests.get(
        f'{BASE_URL}/coverage/{name}',
        headers={'Authorization': api_key},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    regions = response.json().get('regions') or []
    if len(regions) != 1 or regions[0].get('id') != name:
        raise ValueError(f'unexpected regions for coverage {name}')
    return as_multipolygon(wkt.loads(regions[0]['shape']))


def as_multipolygon(shape):
    """Return a shape as a valid multipolygon."""
    if isinstance(shape, Polygon):
        shape = MultiPolygon([shape])
    if not isinstance(shape, MultiPolygon) or shape.is_empty or not shape.is_valid:
        raise ValueError(f'not a valid multipolygon: {shape.geom_type}')
    return shape


def save(shapes):
    """Replace the coverages saved with these, {name: multipolygon}."""
    with commit_or_rollback(DBSession):
        DBSession.query(NavitiaCoverage).delete()
        DBSession.add_all(
            NavitiaCoverage(
                coverage_type=name,
                geom=from_shape(shape, srid=SRID),
                updated_at=func.now(),
            )
            for name, shape in shapes.items()
        )


if __name__ == '__main__':
    main()
