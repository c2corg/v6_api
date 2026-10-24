from c2corg_api.models.outing import Outing, OutingLocale
from c2corg_api.tests import BaseTestCase


class TestOuting(BaseTestCase):
    def test_to_archive(self):
        outing = Outing(
            document_id=1,
            activities=['skitouring'],
            elevation_max=1200,
            locales=[
                OutingLocale(
                    id=2,
                    lang='en',
                    title='A',
                    description='abc',
                    route_description='...',
                ),
                OutingLocale(
                    id=3,
                    lang='fr',
                    title='B',
                    description='bcd',
                    route_description='...',
                ),
            ],
        )

        outing_archive = outing.to_archive()

        assert outing_archive.id is None
        assert outing_archive.document_id == outing.document_id
        assert outing_archive.activities == outing.activities
        assert outing_archive.elevation_max == outing.elevation_max

        archive_locals = outing.get_archive_locales()

        assert len(archive_locals) == 2
        locale = outing.locales[0]
        locale_archive = archive_locals[0]
        assert locale_archive is not locale
        assert locale_archive.id is None
        assert locale_archive.lang == locale.lang
        assert locale_archive.title == locale.title
        assert locale_archive.description == locale.description
        assert locale_archive.route_description == locale.route_description
