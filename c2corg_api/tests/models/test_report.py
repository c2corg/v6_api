from c2corg_api.models.report import Report, ReportLocale

from c2corg_api.tests import BaseTestCase


class TestReport(BaseTestCase):

    def test_to_archive(self):
        report = Report(
            document_id=1,
            activities=['skitouring'],
            event_type=['avalanche'],
            nb_participants=5,
            elevation=1200,
            locales=[
                ReportLocale(
                    id=2, lang='en', title='A', description='abc',
                    place='abcdef',
                    route_study='blabla route study...',
                    conditions='blablabla conditions...'),
                ReportLocale(
                    id=3, lang='fr', title='B', description='bcd',
                    place='abcdef',
                    route_study='blabla route study...',
                    conditions='blablabla conditions...')
            ]
        )

        report_archive = report.to_archive()

        self.assertIsNone(report_archive.id)
        self.assertEqual(report_archive.document_id, report.document_id)
        self.assertEqual(
            report_archive.activities, report.activities)
        self.assertEqual(report_archive.event_type, report.event_type)
        self.assertEqual(
            report_archive.nb_participants, report.nb_participants)
        self.assertEqual(report_archive.elevation, report.elevation)

        self.assertIsNotNone(report_archive.activities)
        self.assertIsNotNone(report_archive.event_type)
        self.assertIsNotNone(report_archive.nb_participants)

        archive_locals = report.get_archive_locales()

        self.assertEqual(len(archive_locals), 2)
        locale = report.locales[0]
        locale_archive = archive_locals[0]
        self.assertIsNot(locale_archive, locale)
        self.assertIsNone(locale_archive.id)
        self.assertEqual(locale_archive.lang, locale.lang)
        self.assertEqual(locale_archive.title, locale.title)
        self.assertEqual(locale_archive.description, locale.description)
