from c2corg_api.models.document import DocumentLocale
from c2corg_api.models.topo_map import TopoMap

from c2corg_api.tests import BaseTestCase


class TestMap(BaseTestCase):

    def test_to_archive(self):
        m = TopoMap(
            document_id=1, editor='ign', scale='20000', code='3431OT',
            locales=[
                DocumentLocale(
                    id=2, lang='en', title='Lac d\'Annecy'),
                DocumentLocale(
                    id=3, lang='fr', title='Lac d\'Annecy'),
            ]
        )

        map_archive = m.to_archive()

        self.assertIsNone(map_archive.id)
        self.assertEqual(map_archive.document_id, m.document_id)
        self.assertEqual(
            map_archive.editor, m.editor)
        self.assertEqual(map_archive.scale, m.scale)
        self.assertEqual(map_archive.code, m.code)

        archive_locals = m.get_archive_locales()

        self.assertEqual(len(archive_locals), 2)
        locale = m.locales[0]
        locale_archive = archive_locals[0]
        self.assertIsNot(locale_archive, locale)
        self.assertIsNone(locale_archive.id)
        self.assertEqual(locale_archive.lang, locale.lang)
        self.assertEqual(locale_archive.title, locale.title)
