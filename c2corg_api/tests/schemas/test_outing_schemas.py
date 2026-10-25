import datetime

from c2corg_api.ext.colander_ext import wkbelement_from_geojson
from c2corg_api.models.document import DocumentGeometry
from c2corg_api.models.outing import (
    Outing,
    OutingLocale,
    schema_create_outing,
    schema_outing,
    schema_update_outing,
)
from c2corg_api.models.schema_utils import restrict_schema
from c2corg_api.schemas.outing import (
    OutingCreateSchema,
    OutingUpdateSchema,
    outing_schema,
)
from c2corg_api.tests.schemas.parity import GEOMETRIES, assert_document_type_parity

LISTING = ['locales.title', 'activities', 'date_start', 'geometry.geom', 'ski_rating']


def test_outing_parity():
    outing = Outing(
        document_id=1,
        version=2,
        activities=['skitouring'],
        date_start=datetime.date(2020, 1, 2),
        date_end=datetime.date(2020, 1, 3),
        elevation_max=1500,
        ski_rating='3.1',
        partial_trip=False,
        locales=[OutingLocale(lang='en', title='Title', version=1, weather='sunny')],
        geometry=DocumentGeometry(
            version=1,
            geom=wkbelement_from_geojson(GEOMETRIES['POINT'], 3857),
            geom_detail=wkbelement_from_geojson(GEOMETRIES['LINESTRING'], 3857),
        ),
    )
    assert_document_type_parity(
        (
            schema_create_outing,
            schema_update_outing,
            schema_outing,
            restrict_schema(schema_outing, LISTING),
        ),
        (
            OutingCreateSchema,
            OutingUpdateSchema,
            outing_schema,
            outing_schema.restrict(LISTING),
        ),
        outing,
    )
