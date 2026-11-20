import datetime
import json

import pytest

from c2corg_api.ext.wkb import geojson_from_wkbelement, wkbelement_from_geojson
from c2corg_api.models.document import DocumentGeometry
from c2corg_api.models.outing import Outing
from c2corg_api.models.route import Route

# The database simplifies the tracks when it saves them (simplify_geom_detail),
# with a tolerance in EPSG:3857 units: 2 for outings, 3 for routes.


def _bend(meters):
    """Return a 200 m line whose middle point is `meters` off the straight line."""
    return wkbelement_from_geojson(
        {
            'type': 'LineString',
            'coordinates': [
                [635000, 5723000],
                [635100, 5723000 + meters],
                [635200, 5723000],
            ],
        },
        3857,
    )


def _saved_points(session, document):
    session.add(document)
    session.flush()
    session.refresh(document.geometry)
    return json.loads(geojson_from_wkbelement(document.geometry.geom_detail))[
        'coordinates'
    ]


@pytest.mark.parametrize(('bend', 'points'), [(1.9, 2), (2.1, 3)])
def test_outings(session, bend, points):
    outing = Outing(
        activities=['hiking'],
        date_start=datetime.date(2026, 11, 19),
        date_end=datetime.date(2026, 11, 19),
        geometry=DocumentGeometry(geom_detail=_bend(bend)),
    )
    assert len(_saved_points(session, outing)) == points


@pytest.mark.parametrize(('bend', 'points'), [(2.9, 2), (3.1, 3)])
def test_routes(session, bend, points):
    route = Route(
        activities=['hiking'], geometry=DocumentGeometry(geom_detail=_bend(bend))
    )
    assert len(_saved_points(session, route)) == points
