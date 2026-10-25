from c2corg_api.ext.colander_ext import wkbelement_from_geojson
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.topo_map import (
    TopoMap,
    schema_listing_topo_map,
    schema_topo_map,
    schema_update_topo_map,
)
from c2corg_api.schemas.topo_map import (
    TopoMapCreateSchema,
    TopoMapUpdateSchema,
    topo_map_listing_schema,
    topo_map_schema,
)
from c2corg_api.tests.schemas.parity import GEOMETRIES, assert_document_type_parity


def test_topo_map_parity():
    topo_map = TopoMap(
        document_id=1,
        version=2,
        editor='IGN',
        scale='25000',
        code='3432OT',
        locales=[DocumentLocale(lang='en', title='Title', version=1)],
        geometry=DocumentGeometry(
            version=1,
            geom_detail=wkbelement_from_geojson(GEOMETRIES['POLYGON'], 3857),
        ),
    )
    assert_document_type_parity(
        (
            schema_topo_map,
            schema_update_topo_map,
            schema_topo_map,
            schema_listing_topo_map,
        ),
        (
            TopoMapCreateSchema,
            TopoMapUpdateSchema,
            topo_map_schema,
            topo_map_listing_schema,
        ),
        topo_map,
    )
