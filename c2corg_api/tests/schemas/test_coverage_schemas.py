from c2corg_api.ext.colander_ext import wkbelement_from_geojson
from c2corg_api.models.coverage import (
    Coverage,
    schema_coverage,
    schema_create_coverage,
    schema_listing_coverage,
    schema_update_coverage,
)
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.schemas.coverage import (
    CoverageCreateSchema,
    CoverageUpdateSchema,
    coverage_listing_schema,
    coverage_schema,
)
from c2corg_api.tests.schemas.parity import GEOMETRIES, assert_document_type_parity


def test_coverage_parity():
    coverage = Coverage(
        document_id=1,
        version=2,
        coverage_type='fr-se',
        locales=[DocumentLocale(lang='en', title='South-East', version=1)],
        geometry=DocumentGeometry(
            version=1,
            geom_detail=wkbelement_from_geojson(GEOMETRIES['POLYGON'], 3857),
        ),
    )
    assert_document_type_parity(
        (
            schema_create_coverage,
            schema_update_coverage,
            schema_coverage,
            schema_listing_coverage,
        ),
        (
            CoverageCreateSchema,
            CoverageUpdateSchema,
            coverage_schema,
            coverage_listing_schema,
        ),
        coverage,
    )
