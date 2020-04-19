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
                    id=2, lang='en', title='A', description='abc',
                    place='abcdef',
                    route_study='blabla route study...',
                    conditions='blablabla conditions...'),
                XreportLocale(
                    id=3, lang='fr', title='B', description='bcd',
                    place='abcdef',
                    route_study='blabla route study...',
                    conditions='blablabla conditions...')
            ]
        )

        xreport_archive = xreport.to_archive()

        self.assertIsNone(xreport_archive.id)
        self.assertEqual(xreport_archive.document_id, xreport.document_id)
        self.assertEqual(
            xreport_archive.event_activity, xreport.event_activity)
        self.assertEqual(xreport_archive.event_type, xreport.event_type)
        self.assertEqual(
            xreport_archive.nb_participants, xreport.nb_participants)
        self.assertEqual(xreport_archive.elevation, xreport.elevation)

        self.assertIsNotNone(xreport_archive.event_activity)
        self.assertIsNotNone(xreport_archive.event_type)
        self.assertIsNotNone(xreport_archive.nb_participants)

        archive_locals = xreport.get_archive_locales()

        self.assertEqual(len(archive_locals), 2)
        locale = xreport.locales[0]
        locale_archive = archive_locals[0]
        self.assertIsNot(locale_archive, locale)
        self.assertIsNone(locale_archive.id)
        self.assertEqual(locale_archive.lang, locale.lang)
        self.assertEqual(locale_archive.title, locale.title)
        self.assertEqual(locale_archive.description, locale.description)
