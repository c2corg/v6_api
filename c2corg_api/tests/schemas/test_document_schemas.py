import colander

from c2corg_api.ext.colander_ext import Geometry as ColanderGeometry
from c2corg_api.models.document import DocumentLocale, schema_document_locale
from c2corg_api.models.schema_utils import SchemaAssociations
from c2corg_api.schemas.base import ModelSchema, Schema
from c2corg_api.schemas.document import (
    AssociationsSchema,
    LocaleSchema,
    geometry_schema,
)
from c2corg_api.tests.schemas.parity import assert_parity
from c2corg_api.views import serialize


def _geometry_node(types):
    class GeometryNode(colander.MappingSchema):
        version = colander.SchemaNode(colander.Integer(), missing=None)
        geom = colander.SchemaNode(
            ColanderGeometry(['POINT'], srid=3857), missing=colander.null
        )
        geom_detail = colander.SchemaNode(
            ColanderGeometry(types, srid=3857), missing=colander.null
        )

    return GeometryNode()


class TestParity:
    def test_locale(self):
        assert_parity(schema_document_locale, LocaleSchema)

    def test_associations(self):
        assert_parity(SchemaAssociations(), AssociationsSchema)

    def test_geometry(self):
        for types in (
            ['POINT'],
            ['LINESTRING', 'MULTILINESTRING'],
            ['POLYGON', 'MULTIPOLYGON'],
        ):
            assert_parity(_geometry_node(types), geometry_schema(types))


class TestSchema:
    def test_unknown_fields_are_ignored(self):
        class Example(Schema):
            name: str

        assert Example.model_validate({'name': 'a', 'other': 1}).model_dump() == {
            'name': 'a'
        }


class TestModelSchema:
    def setup_method(self):
        self.colander = schema_document_locale
        self.schema = ModelSchema(DocumentLocale, LocaleSchema)

    def test_dictify(self):
        locale = DocumentLocale(lang='fr', title='Titre', version=3, summary=None)
        assert serialize(self.schema.dictify(locale)) == serialize(
            self.colander.dictify(locale)
        )

    def test_objectify(self):
        data = {'lang': 'fr', 'title': 'Titre', 'version': None, 'description': 'd'}
        expected = self.colander.objectify(data)
        actual = self.schema.objectify(data)
        for name in ('lang', 'title', 'version', 'description', 'summary'):
            assert getattr(actual, name) == getattr(expected, name)

    def test_only(self):
        locale = DocumentLocale(lang='fr', title='Titre', version=3)
        assert self.schema.only(['lang', 'title']).dictify(locale) == {
            'lang': 'fr',
            'title': 'Titre',
        }
