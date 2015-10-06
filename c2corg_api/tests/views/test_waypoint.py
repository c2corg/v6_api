from c2corg_api.models.waypoint import (
    Waypoint, WaypointLocale, ArchiveWaypoint, ArchiveWaypointLocale)
from c2corg_api.views.document import DocumentRest

from c2corg_api.tests.views import BaseTestRest


class TestWaypointRest(BaseTestRest):

    def setUp(self):  # noqa
        self.set_prefix_and_model(
            "/waypoints", Waypoint, ArchiveWaypoint, ArchiveWaypointLocale)
        BaseTestRest.setUp(self)
        self._add_test_data()

    def test_get_collection(self):
        self.get_collection()

    def test_get(self):
        self.get(self.waypoint)

    def test_get_lang(self):
        self.get_lang(self.waypoint)

    def test_post_error(self):
        body = self.post_error({})
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertMissing(errors[0], 'waypoint_type')

    def test_post_missing_title(self):
        body = {
            'waypoint_type': 'summit',
            'elevation': 3200,
            'locales': [
                {'culture': 'en'}
            ]
        }
        self.post_missing_title(body)

    def test_post_non_whitelisted_attribute(self):
        body = {
            'waypoint_type': 'summit',
            'elevation': 3779,
            'protected': True,
            'locales': [
                {'culture': 'en', 'title': 'Mont Pourri',
                 'pedestrian_access': 'y'}
            ]
        }
        self.post_non_whitelisted_attribute(body)

    def test_post_success(self):
        body = {
            'waypoint_type': 'summit',
            'elevation': 3779,
            'locales': [
                {'culture': 'en', 'title': 'Mont Pourri',
                 'pedestrian_access': 'y'}
            ]
        }
        body, doc = self.post_success(body)
        version = doc.versions[0]

        archive_waypoint = version.document_archive
        self.assertEqual(archive_waypoint.waypoint_type, 'summit')
        self.assertEqual(archive_waypoint.elevation, 3779)

        archive_locale = version.document_locales_archive
        self.assertEqual(archive_locale.culture, 'en')
        self.assertEqual(archive_locale.title, 'Mont Pourri')
        self.assertEqual(archive_locale.pedestrian_access, 'y')

    def test_put_wrong_document_id(self):
        body = {
            'document': {
                'document_id': '-9999',
                'version': self.waypoint.version,
                'waypoint_type': 'summit',
                'elevation': 1234,
                'locales': [
                    {'culture': 'en', 'title': 'Mont Granier',
                     'description': '...', 'pedestrian_access': 'n'}
                ]
            }
        }
        self.put_wrong_document_id(body)

    def test_put_wrong_document_version(self):
        body = {
            'document': {
                'document_id': self.waypoint.document_id,
                'version': -9999,
                'waypoint_type': 'summit',
                'elevation': 1234,
                'locales': [
                    {'culture': 'en', 'title': 'Mont Granier',
                     'description': '...', 'pedestrian_access': 'n'}
                ]
            }
        }
        self.put_wrong_version(body, self.waypoint.document_id)

    def test_put_wrong_locale_version(self):
        body = {
            'document': {
                'document_id': self.waypoint.document_id,
                'version': self.waypoint.version,
                'waypoint_type': 'summit',
                'elevation': 1234,
                'locales': [
                    {'culture': 'en', 'title': 'Mont Granier',
                     'description': '...', 'pedestrian_access': 'n',
                     'version': -9999}
                ]
            }
        }
        self.put_wrong_version(body, self.waypoint.document_id)

    def test_put_wrong_ids(self):
        body = {
            'document': {
                'document_id': self.waypoint.document_id,
                'version': self.waypoint.version,
                'waypoint_type': 'summit',
                'elevation': 1234,
                'locales': [
                    {'culture': 'en', 'title': 'Mont Granier',
                     'description': 'A.', 'pedestrian_access': 'n',
                     'version': self.locale_en.version}
                ]
            }
        }
        self.put_wrong_ids(body, self.waypoint.document_id)

    def test_put_no_document(self):
        self.put_put_no_document(self.waypoint.document_id)

    def test_put_success_all(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.waypoint.document_id,
                'version': self.waypoint.version,
                'waypoint_type': 'summit',
                'elevation': 1234,
                'locales': [
                    {'culture': 'en', 'title': 'Mont Granier',
                     'description': 'A.', 'pedestrian_access': 'n',
                     'version': self.locale_en.version}
                ]
            }
        }
        (body, waypoint) = self.put_success_all(body, self.waypoint)

        self.assertEquals(waypoint.elevation, 1234)
        locale_en = waypoint.get_locale('en')
        self.assertEquals(locale_en.description, 'A.')
        self.assertEquals(locale_en.pedestrian_access, 'n')

        # version with culture 'en'
        versions = waypoint.versions
        version_en = versions[2]
        archive_locale = version_en.document_locales_archive
        self.assertEqual(archive_locale.title, 'Mont Granier')
        self.assertEqual(archive_locale.pedestrian_access, 'n')

        archive_document_en = version_en.document_archive
        self.assertEqual(archive_document_en.waypoint_type, 'summit')
        self.assertEqual(archive_document_en.elevation, 1234)

        # version with culture 'fr'
        version_fr = versions[3]
        archive_locale = version_fr.document_locales_archive
        self.assertEqual(archive_locale.title, 'Mont Granier')
        self.assertEqual(archive_locale.pedestrian_access, 'ouai')

    def test_put_success_figures_only(self):
        """Test updating a document with only changes to the figures.
        """
        body = {
            'message': 'Changing figures',
            'document': {
                'document_id': self.waypoint.document_id,
                'version': self.waypoint.version,
                'waypoint_type': 'summit',
                'elevation': 1234,
                'locales': [
                    {'culture': 'en', 'title': 'Mont Granier',
                     'description': '...', 'pedestrian_access': 'yep',
                     'version': self.locale_en.version}
                ]
            }
        }
        (body, waypoint) = self.put_success_figures_only(body, self.waypoint)

        self.assertEquals(waypoint.elevation, 1234)

    def test_put_success_lang_only(self):
        """Test updating a document with only changes to a locale.
        """
        body = {
            'message': 'Changing lang',
            'document': {
                'document_id': self.waypoint.document_id,
                'version': self.waypoint.version,
                'waypoint_type': 'summit',
                'elevation': 2203,
                'locales': [
                    {'culture': 'en', 'title': 'Mont Granier',
                     'description': '...', 'pedestrian_access': 'no',
                     'version': self.locale_en.version}
                ]
            }
        }
        (body, waypoint) = self.put_success_lang_only(body, self.waypoint)

        self.assertEquals(waypoint.get_locale('en').pedestrian_access, 'no')

    def test_put_success_new_lang(self):
        """Test updating a document by adding a new locale.
        """
        body = {
            'message': 'Adding lang',
            'document': {
                'document_id': self.waypoint.document_id,
                'version': self.waypoint.version,
                'waypoint_type': 'summit',
                'elevation': 2203,
                'locales': [
                    {'culture': 'es', 'title': 'Mont Granier',
                     'description': '...', 'pedestrian_access': 'si'}
                ]
            }
        }
        (body, waypoint) = self.put_success_new_lang(body, self.waypoint)

        self.assertEquals(waypoint.get_locale('es').pedestrian_access, 'si')

    def _add_test_data(self):
        self.waypoint = Waypoint(
            waypoint_type='summit', elevation=2203)

        self.locale_en = WaypointLocale(
            culture='en', title='Mont Granier', description='...',
            pedestrian_access='yep')

        self.locale_fr = WaypointLocale(
            culture='fr', title='Mont Granier', description='...',
            pedestrian_access='ouai')

        self.waypoint.locales.append(self.locale_en)
        self.waypoint.locales.append(self.locale_fr)

        self.session.add(self.waypoint)
        self.session.flush()

        DocumentRest(None)._create_new_version(self.waypoint)
