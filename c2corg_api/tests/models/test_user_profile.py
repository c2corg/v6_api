from c2corg_api.models.document import DocumentLocale
from c2corg_api.models.user_profile import UserProfile
from c2corg_api.tests import BaseTestCase


class TestUserProfile(BaseTestCase):
    def test_to_archive(self):
        user_profile = UserProfile(
            document_id=1,
            categories=['amateur'],
            locales=[
                DocumentLocale(id=2, lang='en', title='Me', summary='...'),
                DocumentLocale(id=3, lang='fr', title='Moi', summary='...'),
            ],
        )

        user_profile_archive = user_profile.to_archive()

        assert user_profile_archive.id is None
        assert user_profile_archive.document_id == user_profile.document_id
        assert user_profile_archive.categories == user_profile.categories

        archive_locals = user_profile.get_archive_locales()

        assert len(archive_locals) == 2
        locale = user_profile.locales[0]
        locale_archive = archive_locals[0]
        assert locale_archive is not locale
        assert locale_archive.id is None
        assert locale_archive.lang == locale.lang
        assert locale_archive.title == locale.title
