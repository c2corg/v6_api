import pytest

from c2corg_api.models.document import DocumentLocale
from c2corg_api.schemas.base import ModelSchema
from c2corg_api.schemas.document import LocaleSchema


@pytest.fixture
def schema():
    """Return the schema of the locales, from the model."""
    return ModelSchema(DocumentLocale, LocaleSchema)


class TestModelSchema:
    def test_dictify(self, schema):
        locale = DocumentLocale(lang='fr', title='Titre', version=3)
        assert schema.dictify(locale) == {
            'version': 3,
            'lang': 'fr',
            'title': 'Titre',
            'description': None,
            'summary': None,
        }

    def test_objectify(self, schema):
        locale = schema.objectify(
            {'lang': 'fr', 'title': 'Titre', 'version': None, 'unknown': 1}
        )
        assert isinstance(locale, DocumentLocale)
        assert (locale.lang, locale.title, locale.version) == ('fr', 'Titre', None)

    def test_only(self, schema):
        locale = DocumentLocale(lang='fr', title='Titre', version=3)
        assert schema.only(['lang', 'title']).dictify(locale) == {
            'lang': 'fr',
            'title': 'Titre',
        }
