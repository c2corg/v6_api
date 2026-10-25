import datetime

from c2corg_api.ext.colander_ext import wkbelement_from_geojson
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.image import (
    Image,
    schema_create_image,
    schema_create_image_list,
    schema_image,
    schema_listing_image,
    schema_update_image,
)
from c2corg_api.schemas.image import (
    ImageCreateSchema,
    ImageListCreateSchema,
    ImageUpdateSchema,
    image_listing_schema,
    image_schema,
)
from c2corg_api.tests.schemas.parity import (
    GEOMETRIES,
    assert_document_type_parity,
    assert_parity,
)


def test_image_parity():
    image = Image(
        document_id=1,
        version=2,
        filename='image.jpg',
        image_type='collaborative',
        activities=['hiking'],
        height=1500,
        exposure_time=0.01,
        date_time=datetime.datetime(2020, 1, 2, 10, 0, tzinfo=datetime.UTC),
        locales=[DocumentLocale(lang='en', title='', version=1)],
        geometry=DocumentGeometry(
            version=1, geom=wkbelement_from_geojson(GEOMETRIES['POINT'], 3857)
        ),
    )
    assert_document_type_parity(
        (schema_create_image, schema_update_image, schema_image, schema_listing_image),
        (ImageCreateSchema, ImageUpdateSchema, image_schema, image_listing_schema),
        image,
    )


def test_image_list_parity():
    assert_parity(schema_create_image_list, ImageListCreateSchema)
