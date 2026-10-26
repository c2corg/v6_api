from c2corg_api.models.document import DocumentLocale
from c2corg_api.schemas.base import ModelSchema
from c2corg_api.schemas.document import LocaleSchema


class TestModelSchema:
    def setup_method(self):
        self.schema = ModelSchema(DocumentLocale, LocaleSchema)

    def test_dictify(self):
        locale = DocumentLocale(lang='fr', title='Titre', version=3)
        assert self.schema.dictify(locale) == {
            'version': 3,
            'lang': 'fr',
            'title': 'Titre',
            'description': None,
            'summary': None,
        }

    def test_objectify(self):
        locale = self.schema.objectify(
            {'lang': 'fr', 'title': 'Titre', 'version': None, 'unknown': 1}
        )
        assert isinstance(locale, DocumentLocale)
        assert (locale.lang, locale.title, locale.version) == ('fr', 'Titre', None)

    def test_only(self):
        locale = DocumentLocale(lang='fr', title='Titre', version=3)
        assert self.schema.only(['lang', 'title']).dictify(locale) == {
            'lang': 'fr',
            'title': 'Titre',
        }
