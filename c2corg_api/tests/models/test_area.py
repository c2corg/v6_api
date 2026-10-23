from c2corg_api.models.area import Area
from c2corg_api.models.document import DocumentLocale
from c2corg_api.tests import BaseTestCase


class TestArea(BaseTestCase):
    def test_to_archive(self):
        area = Area(
            document_id=1,
            area_type='range',
            locales=[
                DocumentLocale(id=2, lang='en', title='Chartreuse', summary='...'),
                DocumentLocale(id=3, lang='fr', title='Chartreuse', summary='...'),
            ],
        )

        area_archive = area.to_archive()

        assert area_archive.id is None
        assert area_archive.document_id == area.document_id
        assert area_archive.area_type == area.area_type

        archive_locals = area.get_archive_locales()

        assert len(archive_locals) == 2
        locale = area.locales[0]
        locale_archive = archive_locals[0]
        assert locale_archive is not locale
        assert locale_archive.id is None
        assert locale_archive.lang == locale.lang
        assert locale_archive.title == locale.title
