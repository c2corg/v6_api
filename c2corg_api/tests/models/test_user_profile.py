from c2corg_api.models.document import DocumentLocale
from c2corg_api.models.user_profile import UserProfile

from c2corg_api.tests import BaseTestCase


class TestUserProfile(BaseTestCase):

    def test_to_archive(self):
        user_profile = UserProfile(
            document_id=1, categories=['amateur'],
            locales=[
                DocumentLocale(
                    id=2, lang='en', title='Me', summary='...'),
                DocumentLocale(
                    id=3, lang='fr', title='Moi', summary='...'),
            ]
        )

        user_profile_archive = user_profile.to_archive()

        self.assertIsNone(user_profile_archive.id)
        self.assertEqual(
            user_profile_archive.document_id, user_profile.document_id)
        self.assertEqual(
            user_profile_archive.categories, user_profile.categories)

        archive_locals = user_profile.get_archive_locales()

        self.assertEqual(len(archive_locals), 2)
        locale = user_profile.locales[0]
        locale_archive = archive_locals[0]
        self.assertIsNot(locale_archive, locale)
        self.assertIsNone(locale_archive.id)
        self.assertEqual(locale_archive.lang, locale.lang)
        self.assertEqual(locale_archive.title, locale.title)
