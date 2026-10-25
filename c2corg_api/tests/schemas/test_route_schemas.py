from c2corg_api.ext.colander_ext import wkbelement_from_geojson
from c2corg_api.models.document import DocumentGeometry
from c2corg_api.models.route import (
    Route,
    RouteLocale,
    schema_create_route,
    schema_route,
    schema_update_route,
)
from c2corg_api.models.schema_utils import restrict_schema
from c2corg_api.schemas.route import RouteCreateSchema, RouteUpdateSchema, route_schema
from c2corg_api.tests.schemas.parity import GEOMETRIES, assert_document_type_parity

LISTING = ['locales.title', 'locales.title_prefix', 'activities', 'ski_rating']


def test_route_parity():
    route = Route(
        document_id=1,
        version=2,
        activities=['skitouring'],
        main_waypoint_id=3,
        elevation_max=1500,
        calculated_duration=0.5,
        ski_rating='3.1',
        lift_access=False,
        durations=['1'],
        locales=[
            RouteLocale(lang='en', title='Title', version=1, title_prefix='Summit')
        ],
        geometry=DocumentGeometry(
            version=1,
            geom=wkbelement_from_geojson(GEOMETRIES['POINT'], 3857),
            geom_detail=wkbelement_from_geojson(GEOMETRIES['LINESTRING'], 3857),
        ),
    )
    assert_document_type_parity(
        (
            schema_create_route,
            schema_update_route,
            schema_route,
            restrict_schema(schema_route, LISTING),
        ),
        (
            RouteCreateSchema,
            RouteUpdateSchema,
            route_schema,
            route_schema.restrict(LISTING),
        ),
        route,
    )
