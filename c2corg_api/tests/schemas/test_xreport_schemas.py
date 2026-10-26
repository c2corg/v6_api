import datetime

from c2corg_api.ext.colander_ext import wkbelement_from_geojson
from c2corg_api.models.document import DocumentGeometry
from c2corg_api.models.xreport import (
    Xreport,
    XreportLocale,
    schema_create_xreport,
    schema_listing_xreport,
    schema_update_xreport,
    schema_xreport,
    schema_xreport_without_personal,
)
from c2corg_api.schemas.xreport import (
    XreportCreateSchema,
    XreportUpdateSchema,
    xreport_listing_schema,
    xreport_schema,
    xreport_without_personal_schema,
)
from c2corg_api.tests.schemas.parity import GEOMETRIES, assert_document_type_parity
from c2corg_api.views import serialize


def _xreport():
    return Xreport(
        document_id=1,
        version=2,
        date=datetime.date(2020, 1, 2),
        event_activity='skitouring',
        event_type='avalanche',
        nb_participants=3,
        rescue=True,
        age=40,
        gender='female',
        anonymous=False,
        locales=[XreportLocale(lang='en', title='Title', version=1, place='Somewhere')],
        geometry=DocumentGeometry(
            version=1, geom=wkbelement_from_geojson(GEOMETRIES['POINT'], 3857)
        ),
    )


def test_xreport_parity():
    assert_document_type_parity(
        (
            schema_create_xreport,
            schema_update_xreport,
            schema_xreport,
            schema_listing_xreport,
        ),
        (
            XreportCreateSchema,
            XreportUpdateSchema,
            xreport_schema,
            xreport_listing_schema,
        ),
        _xreport(),
    )


def test_xreport_without_personal():
    xreport = _xreport()
    assert serialize(xreport_without_personal_schema.dictify(xreport)) == serialize(
        schema_xreport_without_personal.dictify(xreport)
    )
