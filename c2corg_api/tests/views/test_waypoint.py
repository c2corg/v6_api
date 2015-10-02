import json

from c2corg_api.models.waypoint import (
    Waypoint, WaypointLocale, ArchiveWaypoint, ArchiveWaypointLocale)
from c2corg_api.views.document import DocumentRest

from c2corg_api.tests.views import BaseTestRest


class TestWaypointRest(BaseTestRest):

    def setUp(self):  # noqa
        self.set_prefix_and_model("/waypoints", Waypoint)
        BaseTestRest.setUp(self)
        self._add_test_data()

    def test_get_collection(self):
        self.get_collection()

    def test_get(self):
        body = self.get(self.waypoint)
        self.assertIsNotNone(body.get('version_hash'))
        locale_en = body.get('locales')[0]
        self.assertIsNotNone(locale_en.get('version_hash'))

    def test_get_lang(self):
        response = self.app.get(
            '/waypoints/' + str(self.waypoint.document_id) + '?l=en')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, 'application/json')

        body = response.json
        locales = body.get('locales')
        self.assertEqual(len(locales), 1)
        locale_en = locales[0]
        self.assertEqual(locale_en.get('culture'), self.locale_en.culture)

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
        response = self.app.post_json(
            '/waypoints', body, expect_errors=True, status=400)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].get('description'), 'Required')
        self.assertEqual(errors[0].get('name'), 'locales.0.title')

    def test_post_non_whitelisted_attribute(self):
        """`protected` is a non-whitelisted attribute, which is ignored when
        given in a request.
        """
        body = {
            'waypoint_type': 'summit',
            'elevation': 3779,
            'protected': True,
            'locales': [
                {'culture': 'en', 'title': 'Mont Pourri',
                 'pedestrian_access': 'y'}
            ]
        }
        response = self.app.post(
            '/waypoints', params=json.dumps(body),
            content_type='application/json')
        self.assertEqual(response.status_code, 200)

        body = json.loads(response.body)
        document_id = body.get('document_id')
        waypoint = self.session.query(Waypoint).get(document_id)
        # the value for `protected` was ignored
        self.assertFalse(waypoint.protected)

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
        self.assertIsNotNone(body.get('version_hash'))
        version = doc.versions[0]

        archive_waypoint = version.document_archive
        self.assertEqual(archive_waypoint.waypoint_type, 'summit')
        self.assertEqual(archive_waypoint.elevation, 3779)
        self.assertEqual(archive_waypoint.version_hash, doc.version_hash)

        archive_locale = version.document_locales_archive
        waypoint_locale_en = doc.locales[0]
        self.assertEqual(
            archive_locale.version_hash, waypoint_locale_en.version_hash)
        self.assertEqual(archive_locale.culture, 'en')
        self.assertEqual(archive_locale.title, 'Mont Pourri')
        self.assertEqual(archive_locale.pedestrian_access, 'y')

    def test_put_wrong_document_id(self):
        body = {
            'document': {
                'document_id': '-9999',
                'version_hash': self.waypoint.version_hash,
                'waypoint_type': 'summit',
                'elevation': 1234,
                'locales': [
                    {'culture': 'en', 'title': 'Mont Granier',
                     'description': '...', 'pedestrian_access': 'n'}
                ]
            }
        }
        response = self.app.put(
            '/waypoints/' + '-9999',
            params=json.dumps(body),
            content_type='application/json',
            expect_errors=True)
        self.assertEqual(response.status_code, 404)

    def test_put_wrong_document_version(self):
        body = {
            'document': {
                'document_id': self.waypoint.document_id,
                'version_hash': 'some-old-version',
                'waypoint_type': 'summit',
                'elevation': 1234,
                'locales': [
                    {'culture': 'en', 'title': 'Mont Granier',
                     'description': '...', 'pedestrian_access': 'n'}
                ]
            }
        }
        response = self.app.put(
            '/waypoints/' + str(self.waypoint.document_id),
            params=json.dumps(body),
            content_type='application/json',
            expect_errors=True)
        self.assertEqual(response.status_code, 409)

    def test_put_wrong_locale_version(self):
        body = {
            'document': {
                'document_id': self.waypoint.document_id,
                'version_hash': self.waypoint.version_hash,
                'waypoint_type': 'summit',
                'elevation': 1234,
                'locales': [
                    {'culture': 'en', 'title': 'Mont Granier',
                     'description': '...', 'pedestrian_access': 'n',
                     'version_hash': 'some-old-version'}
                ]
            }
        }
        response = self.app.put(
            '/waypoints/' + str(self.waypoint.document_id),
            params=json.dumps(body),
            content_type='application/json',
            expect_errors=True)
        self.assertEqual(response.status_code, 409)

    def test_put_wrong_ids(self):
        """The id given in the URL does not equal the document_id in the
        request body.
        """
        body = {
            'document': {
                'document_id': self.waypoint.document_id,
                'version_hash': self.waypoint.version_hash,
                'waypoint_type': 'summit',
                'elevation': 1234,
                'locales': [
                    {'culture': 'en', 'title': 'Mont Granier',
                     'description': 'A.', 'pedestrian_access': 'n',
                     'version_hash': self.locale_en.version_hash}
                ]
            }
        }
        response = self.app.put(
            '/waypoints/' + str(self.waypoint.document_id + 1),
            params=json.dumps(body),
            content_type='application/json',
            expect_errors=True)
        self.assertEqual(response.status_code, 400)

    def test_put_no_document(self):
        body = {
            'message': '...'
        }
        response = self.app.put(
            '/waypoints/' + str(self.waypoint.document_id),
            params=json.dumps(body),
            content_type='application/json',
            expect_errors=True)
        self.assertEqual(response.status_code, 400)

    def test_put_success_all(self):
        """Test updating a document with changes to the figures and locales.
        """
        body = {
            'message': 'Changing elevation and access',
            'document': {
                'document_id': self.waypoint.document_id,
                'version_hash': self.waypoint.version_hash,
                'waypoint_type': 'summit',
                'elevation': 1234,
                'locales': [
                    {'culture': 'en', 'title': 'Mont Granier',
                     'description': 'A.', 'pedestrian_access': 'n',
                     'version_hash': self.locale_en.version_hash}
                ]
            }
        }
        response = self.app.put(
            '/waypoints/' + str(self.waypoint.document_id),
            params=json.dumps(body),
            content_type='application/json')
        self.assertEqual(response.status_code, 200)

        body = json.loads(response.body)
        document_id = body.get('document_id')
        self.assertNotEquals(
            body.get('version_hash'), self.waypoint.version_hash)
        self.assertEquals(body.get('document_id'), document_id)

        # check that the waypoint was updated correctly
        self.session.expire_all()
        waypoint = self.session.query(Waypoint).get(document_id)
        self.assertEquals(waypoint.elevation, 1234)
        self.assertEquals(len(waypoint.locales), 2)
        locale_en = waypoint.get_locale('en')
        self.assertEquals(locale_en.description, 'A.')
        self.assertEquals(locale_en.pedestrian_access, 'n')

        # check that a new archive_document was created
        archive_count = self.session.query(ArchiveWaypoint). \
            filter(ArchiveWaypoint.document_id == document_id).count()
        self.assertEqual(archive_count, 2)

        # check that only one new archive_document_locale was created (only
        # for 'en' not 'fr')
        archive_locale_count = self.session.query(ArchiveWaypointLocale). \
            filter(ArchiveWaypointLocale.document_id == document_id).count()
        self.assertEqual(archive_locale_count, 3)

        # check that new versions were created
        versions = waypoint.versions
        self.assertEqual(len(versions), 4)

        # version with culture 'en'
        version_en = versions[2]

        self.assertEqual(version_en.culture, 'en')
        self.assertEqual(version_en.version, 999)

        meta_data_en = version_en.history_metadata
        self.assertEqual(meta_data_en.comment, 'Changing elevation and access')
        self.assertIsNotNone(meta_data_en.written_at)

        archive_waypoint_en = version_en.document_archive
        self.assertEqual(archive_waypoint_en.document_id, document_id)
        self.assertEqual(archive_waypoint_en.waypoint_type, 'summit')
        self.assertEqual(archive_waypoint_en.elevation, 1234)
        self.assertEqual(
            archive_waypoint_en.version_hash, waypoint.version_hash)

        archive_locale = version_en.document_locales_archive
        self.assertEqual(archive_locale.document_id, document_id)
        self.assertEqual(archive_locale.version_hash, locale_en.version_hash)
        self.assertEqual(archive_locale.culture, 'en')
        self.assertEqual(archive_locale.title, 'Mont Granier')
        self.assertEqual(archive_locale.pedestrian_access, 'n')

        # version with culture 'fr'
        version_fr = versions[3]

        self.assertEqual(version_fr.culture, 'fr')
        self.assertEqual(version_fr.version, 999)

        meta_data_fr = version_fr.history_metadata
        self.assertIs(meta_data_en, meta_data_fr)

        archive_waypoint_fr = version_fr.document_archive
        self.assertIs(archive_waypoint_en, archive_waypoint_fr)

        archive_locale = version_fr.document_locales_archive
        self.assertEqual(archive_locale.document_id, document_id)
        self.assertEqual(
            archive_locale.version_hash, self.locale_fr.version_hash)
        self.assertEqual(archive_locale.culture, 'fr')
        self.assertEqual(archive_locale.title, 'Mont Granier')
        self.assertEqual(archive_locale.pedestrian_access, 'ouai')

    def test_put_success_figures_only(self):
        """Test updating a document with only changes to the figures.
        """
        body = {
            'message': 'Changing elevation',
            'document': {
                'document_id': self.waypoint.document_id,
                'version_hash': self.waypoint.version_hash,
                'waypoint_type': 'summit',
                'elevation': 1234,
                'locales': [
                    {'culture': 'en', 'title': 'Mont Granier',
                     'description': '...', 'pedestrian_access': 'yep',
                     'version_hash': self.locale_en.version_hash}
                ]
            }
        }
        response = self.app.put(
            '/waypoints/' + str(self.waypoint.document_id),
            params=json.dumps(body),
            content_type='application/json')
        self.assertEqual(response.status_code, 200)

        body = json.loads(response.body)
        document_id = body.get('document_id')
        self.assertNotEquals(
            body.get('version_hash'), self.waypoint.version_hash)
        self.assertEquals(body.get('document_id'), document_id)

        # check that the waypoint was updated correctly
        self.session.expire_all()
        waypoint = self.session.query(Waypoint).get(document_id)
        self.assertEquals(waypoint.elevation, 1234)
        self.assertEquals(len(waypoint.locales), 2)

        # check that a new archive_document was created
        archive_count = self.session.query(ArchiveWaypoint). \
            filter(ArchiveWaypoint.document_id == document_id).count()
        self.assertEqual(archive_count, 2)

        # check that no new archive_document_locale was created
        archive_locale_count = self.session.query(ArchiveWaypointLocale). \
            filter(ArchiveWaypointLocale.document_id == document_id).count()
        self.assertEqual(archive_locale_count, 2)

        # check that new versions were created
        versions = waypoint.versions
        self.assertEqual(len(versions), 4)

        # version with culture 'en'
        version_en = versions[2]

        self.assertEqual(version_en.culture, 'en')
        self.assertEqual(version_en.version, 999)

        meta_data_en = version_en.history_metadata
        self.assertEqual(meta_data_en.comment, 'Changing elevation')
        self.assertIsNotNone(meta_data_en.written_at)

        # version with culture 'fr'
        version_fr = versions[3]

        self.assertEqual(version_fr.culture, 'fr')
        self.assertEqual(version_fr.version, 999)

        meta_data_fr = version_fr.history_metadata
        self.assertIs(meta_data_en, meta_data_fr)

        archive_waypoint_en = version_en.document_archive
        archive_waypoint_fr = version_fr.document_archive
        self.assertIs(archive_waypoint_en, archive_waypoint_fr)

    def test_put_success_lang_only(self):
        """Test updating a document with only changes to a locale.
        """
        body = {
            'message': 'Changing access',
            'document': {
                'document_id': self.waypoint.document_id,
                'version_hash': self.waypoint.version_hash,
                'waypoint_type': 'summit',
                'elevation': 2203,
                'locales': [
                    {'culture': 'en', 'title': 'Mont Granier',
                     'description': '...', 'pedestrian_access': 'no',
                     'version_hash': self.locale_en.version_hash}
                ]
            }
        }
        response = self.app.put(
            '/waypoints/' + str(self.waypoint.document_id),
            params=json.dumps(body),
            content_type='application/json')
        self.assertEqual(response.status_code, 200)

        body = json.loads(response.body)
        document_id = body.get('document_id')
        # document version does not change!
        self.assertEquals(body.get('version_hash'), self.waypoint.version_hash)
        self.assertEquals(body.get('document_id'), document_id)

        # check that the waypoint was updated correctly
        self.session.expire_all()
        waypoint = self.session.query(Waypoint).get(document_id)
        self.assertEquals(waypoint.get_locale('en').pedestrian_access, 'no')
        self.assertEquals(len(waypoint.locales), 2)

        # check that no new archive_document was created
        archive_count = self.session.query(ArchiveWaypoint). \
            filter(ArchiveWaypoint.document_id == document_id).count()
        self.assertEqual(archive_count, 1)

        # check that one new archive_document_locale was created
        archive_locale_count = self.session.query(ArchiveWaypointLocale). \
            filter(ArchiveWaypointLocale.document_id == document_id).count()
        self.assertEqual(archive_locale_count, 3)

        # check that one new version was created
        versions = waypoint.versions
        self.assertEqual(len(versions), 3)

        # version with culture 'en'
        version_en = versions[2]

        self.assertEqual(version_en.culture, 'en')
        self.assertEqual(version_en.version, 999)

        meta_data_en = version_en.history_metadata
        self.assertEqual(meta_data_en.comment, 'Changing access')
        self.assertIsNotNone(meta_data_en.written_at)

        # version with culture 'fr'
        version_fr = versions[1]

        self.assertEqual(version_fr.culture, 'fr')
        self.assertEqual(version_fr.version, 1)

        meta_data_fr = version_fr.history_metadata
        self.assertIsNot(meta_data_en, meta_data_fr)

        archive_waypoint_en = version_en.document_archive
        archive_waypoint_fr = version_fr.document_archive
        self.assertIs(archive_waypoint_en, archive_waypoint_fr)

    def test_put_success_new_lang(self):
        """Test updating a document by adding a new locale.
        """
        body = {
            'message': 'Changing access',
            'document': {
                'document_id': self.waypoint.document_id,
                'version_hash': self.waypoint.version_hash,
                'waypoint_type': 'summit',
                'elevation': 2203,
                'locales': [
                    {'culture': 'es', 'title': 'Mont Granier',
                     'description': '...', 'pedestrian_access': 'si'}
                ]
            }
        }
        response = self.app.put(
            '/waypoints/' + str(self.waypoint.document_id),
            params=json.dumps(body),
            content_type='application/json')
        self.assertEqual(response.status_code, 200)

        body = json.loads(response.body)
        document_id = body.get('document_id')
        # document version does not change!
        self.assertEquals(body.get('version_hash'), self.waypoint.version_hash)
        self.assertEquals(body.get('document_id'), document_id)

        # check that the waypoint was updated correctly
        self.session.expire_all()
        waypoint = self.session.query(Waypoint).get(document_id)
        self.assertEquals(waypoint.get_locale('es').pedestrian_access, 'si')
        self.assertEquals(len(waypoint.locales), 3)

        # check that no new archive_document was created
        archive_count = self.session.query(ArchiveWaypoint). \
            filter(ArchiveWaypoint.document_id == document_id).count()
        self.assertEqual(archive_count, 1)

        # check that one new archive_document_locale was created
        archive_locale_count = self.session.query(ArchiveWaypointLocale). \
            filter(ArchiveWaypointLocale.document_id == document_id).count()
        self.assertEqual(archive_locale_count, 3)

        # check that one new version was created
        versions = waypoint.versions
        self.assertEqual(len(versions), 3)

        # version with culture 'en'
        version_en = versions[0]

        self.assertEqual(version_en.culture, 'en')
        self.assertEqual(version_en.version, 1)

        meta_data_en = version_en.history_metadata

        # version with culture 'fr'
        version_fr = versions[1]

        self.assertEqual(version_fr.culture, 'fr')
        self.assertEqual(version_fr.version, 1)

        meta_data_fr = version_fr.history_metadata
        self.assertIs(meta_data_en, meta_data_fr)

        archive_waypoint_en = version_en.document_archive
        archive_waypoint_fr = version_fr.document_archive
        self.assertIs(archive_waypoint_en, archive_waypoint_fr)

        # version with culture 'es'
        version_es = versions[2]

        self.assertEqual(version_es.culture, 'es')
        self.assertEqual(version_es.version, 999)

        meta_data_es = version_es.history_metadata
        self.assertIsNot(meta_data_en, meta_data_es)

        archive_waypoint_es = version_es.document_archive
        self.assertIs(archive_waypoint_es, archive_waypoint_fr)

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
