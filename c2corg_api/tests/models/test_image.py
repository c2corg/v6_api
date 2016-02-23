from c2corg_api.models.document import DocumentLocale
from c2corg_api.models.image import Image

from c2corg_api.tests import BaseTestCase


class TestImage(BaseTestCase):

    def test_to_archive(self):
        image = Image(
            document_id=1, activities=['skitouring'], height=1200,
            locales=[
                DocumentLocale(
                    id=2, lang='en', title='A', description='abc'),
                DocumentLocale(
                    id=3, lang='fr', title='B', description='bcd'),
            ]
        )

        image_archive = image.to_archive()

        self.assertIsNone(image_archive.id)
        self.assertEqual(image_archive.document_id, image.document_id)
        self.assertEqual(
            image_archive.activities, image.activities)
        self.assertEqual(image_archive.height, image.height)

        archive_locals = image.get_archive_locales()

        self.assertEqual(len(archive_locals), 2)
        locale = image.locales[0]
        locale_archive = archive_locals[0]
        self.assertIsNot(locale_archive, locale)
        self.assertIsNone(locale_archive.id)
        self.assertEqual(locale_archive.lang, locale.lang)
        self.assertEqual(locale_archive.title, locale.title)
        self.assertEqual(locale_archive.description, locale.description)
