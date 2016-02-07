from c2corg_api.models.area import Area
from c2corg_api.models.document import DocumentLocale

from c2corg_api.tests import BaseTestCase


class TestArea(BaseTestCase):

    def test_to_archive(self):
        area = Area(
            document_id=1, area_type='range',
            locales=[
                DocumentLocale(
                    id=2, lang='en', title='Chartreuse', summary='...'),
                DocumentLocale(
                    id=3, lang='fr', title='Chartreuse', summary='...'),
            ]
        )

        area_archive = area.to_archive()

        self.assertIsNone(area_archive.id)
        self.assertEqual(area_archive.document_id, area.document_id)
        self.assertEqual(area_archive.area_type, area.area_type)

        archive_locals = area.get_archive_locales()

        self.assertEqual(len(archive_locals), 2)
        locale = area.locales[0]
        locale_archive = archive_locals[0]
        self.assertIsNot(locale_archive, locale)
        self.assertIsNone(locale_archive.id)
        self.assertEqual(locale_archive.lang, locale.lang)
        self.assertEqual(locale_archive.title, locale.title)
