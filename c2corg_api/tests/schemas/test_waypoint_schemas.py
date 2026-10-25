from c2corg_api.ext.colander_ext import wkbelement_from_geojson
from c2corg_api.models.document import DocumentGeometry
from c2corg_api.models.schema_utils import restrict_schema
from c2corg_api.models.waypoint import (
    Waypoint,
    WaypointLocale,
    schema_create_waypoint,
    schema_update_waypoint,
    schema_waypoint,
)
from c2corg_api.schemas.waypoint import (
    WaypointCreateSchema,
    WaypointUpdateSchema,
    waypoint_schema,
)
from c2corg_api.tests.schemas.parity import GEOMETRIES, assert_document_type_parity

LISTING = ['locales.title', 'elevation', 'waypoint_type', 'geometry.geom']


def test_waypoint_parity():
    waypoint = Waypoint(
        document_id=1,
        version=2,
        waypoint_type='summit',
        elevation=3779,
        lift_access=False,
        rock_types=['basalte'],
        locales=[WaypointLocale(lang='en', title='Mont Pourri', version=1, access='y')],
        geometry=DocumentGeometry(
            version=1, geom=wkbelement_from_geojson(GEOMETRIES['POINT'], 3857)
        ),
    )
    assert_document_type_parity(
        (
            schema_create_waypoint,
            schema_update_waypoint,
            schema_waypoint,
            restrict_schema(schema_waypoint, LISTING),
        ),
        (
            WaypointCreateSchema,
            WaypointUpdateSchema,
            waypoint_schema,
            waypoint_schema.restrict(LISTING),
        ),
        waypoint,
    )
