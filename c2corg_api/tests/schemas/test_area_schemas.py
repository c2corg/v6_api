from c2corg_api.ext.colander_ext import wkbelement_from_geojson
from c2corg_api.models.area import (
    Area,
    schema_area,
    schema_create_area,
    schema_listing_area,
    schema_update_area,
)
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.schemas.area import (
    AreaCreateSchema,
    AreaUpdateSchema,
    area_listing_schema,
    area_schema,
)
from c2corg_api.tests.schemas.parity import GEOMETRIES, assert_document_type_parity


def test_area_parity():
    area = Area(
        document_id=1,
        version=2,
        area_type='range',
        locales=[DocumentLocale(lang='en', title='Chartreuse', version=1)],
        geometry=DocumentGeometry(
            version=1,
            geom_detail=wkbelement_from_geojson(GEOMETRIES['POLYGON'], 3857),
        ),
    )
    assert_document_type_parity(
        (schema_create_area, schema_update_area, schema_area, schema_listing_area),
        (AreaCreateSchema, AreaUpdateSchema, area_schema, area_listing_schema),
        area,
    )
