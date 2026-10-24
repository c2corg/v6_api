from c2corg_api.models.xreport import Xreport, XreportLocale
from c2corg_api.tests import BaseTestCase


class TestXreport(BaseTestCase):
    def test_to_archive(self):
        xreport = Xreport(
            document_id=1,
            event_activity='skitouring',
            event_type='avalanche',
            nb_participants=5,
            elevation=1200,
            locales=[
                XreportLocale(
                    id=2,
                    lang='en',
                    title='A',
                    description='abc',
                    place='abcdef',
                    route_study='blabla route study...',
                    conditions='blablabla conditions...',
                ),
                XreportLocale(
                    id=3,
                    lang='fr',
                    title='B',
                    description='bcd',
                    place='abcdef',
                    route_study='blabla route study...',
                    conditions='blablabla conditions...',
                ),
            ],
        )

        xreport_archive = xreport.to_archive()

        assert xreport_archive.id is None
        assert xreport_archive.document_id == xreport.document_id
        assert xreport_archive.event_activity == xreport.event_activity
        assert xreport_archive.event_type == xreport.event_type
        assert xreport_archive.nb_participants == xreport.nb_participants
        assert xreport_archive.elevation == xreport.elevation

        assert xreport_archive.event_activity is not None
        assert xreport_archive.event_type is not None
        assert xreport_archive.nb_participants is not None

        archive_locals = xreport.get_archive_locales()

        assert len(archive_locals) == 2
        locale = xreport.locales[0]
        locale_archive = archive_locals[0]
        assert locale_archive is not locale
        assert locale_archive.id is None
        assert locale_archive.lang == locale.lang
        assert locale_archive.title == locale.title
        assert locale_archive.description == locale.description
