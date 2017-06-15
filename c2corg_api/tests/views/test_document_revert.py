from c2corg_api.models.association import Association
from c2corg_api.models.document import DocumentGeometry, UpdateType
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.feed import update_feed_document_create
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.views.document import DocumentRest
from c2corg_api.tests.views import BaseTestRest
from json import loads


class TestDocumentRevertRest(BaseTestRest):

    def setUp(self):  # noqa
        super(TestDocumentRevertRest, self).setUp()
        self._prefix = '/documents/revert'
        self._add_test_data()

    def test_revert_unauthorized(self):
        self.app_post_json(self._prefix, {}, status=403)

        headers = self.add_authorization_header(username='contributor')
        self.app_post_json(self._prefix, {}, headers=headers, status=403)

    def test_revert_invalid_document_id(self):
        request_body = {
            'document_id': -1,
            'lang': 'en',
            'version_id': 123456
        }

        headers = self.add_authorization_header(username='moderator')
        self.app_post_json(
            self._prefix, request_body, status=400, headers=headers)

    def test_revert_invalid_version_id(self):
        document_id = self.waypoint2.document_id
        lang = 'en'
        version_id = 123456
        request_body = {
            'document_id': document_id,
            'lang': lang,
            'version_id': version_id
        }

        headers = self.add_authorization_header(username='moderator')
        response = self.app_post_json(
            self._prefix, request_body, status=400, headers=headers)
        self.assertErrorsContain(
            response.json, 'Bad Request',
            'Unknown version {}/{}/{}'.format(document_id, lang, version_id))

    def test_revert_latest_version_id(self):
        document_id = self.waypoint2.document_id
        lang = 'en'
        # Get version id of the latest version of the document:
        version_id, = self.session.query(DocumentVersion.id). \
            filter(DocumentVersion.document_id == document_id). \
            filter(DocumentVersion.lang == lang). \
            order_by(DocumentVersion.id.desc()).first()
        request_body = {
            'document_id': document_id,
            'lang': lang,
            'version_id': version_id
        }

        headers = self.add_authorization_header(username='moderator')
        response = self.app_post_json(
            self._prefix, request_body, status=400, headers=headers)
        self.assertErrorsContain(
            response.json, 'Bad Request',
            'Version {}/{}/{} is already the latest one'.format(
                document_id, lang, version_id))

    def test_revert_waypoint(self):
        document_id = self.waypoint2.document_id
        lang = 'en'
        # Get version id of the first version of the document:
        version_id, = self.session.query(DocumentVersion.id). \
            filter(DocumentVersion.document_id == document_id). \
            filter(DocumentVersion.lang == lang). \
            order_by(DocumentVersion.id.asc()).first()

        initial_count = self.session.query(DocumentVersion). \
            filter(DocumentVersion.document_id == document_id). \
            filter(DocumentVersion.lang == lang).count()

        request_body = {
            'document_id': document_id,
            'lang': lang,
            'version_id': version_id
        }

        headers = self.add_authorization_header(username='moderator')
        self.app_post_json(
            self._prefix, request_body, status=200, headers=headers)

        response = self.app.get('/waypoints/' + str(document_id), status=200)
        body = response.json
        self.assertEqual(body['elevation'], 4810)
        geom = loads(body['geometry']['geom'])
        self.assertEqual(geom['coordinates'][0], 635957)
        self.assertEqual(geom['coordinates'][1], 5723605)
        for locale in body['locales']:
            if locale['lang'] == lang:
                self.assertEqual(
                    locale['summary'], 'The highest point in Europe')

        # check a new version has been created
        count = self.session.query(DocumentVersion). \
            filter(DocumentVersion.document_id == document_id). \
            filter(DocumentVersion.lang == lang).count()
        self.assertEqual(count, initial_count + 1)

    def test_revert_route(self):
        route_id = self.route1.document_id
        route_lang = 'fr'
        # Get version id of the first version of the document:
        route_version_id, = self.session.query(DocumentVersion.id). \
            filter(DocumentVersion.document_id == route_id). \
            filter(DocumentVersion.lang == route_lang). \
            order_by(DocumentVersion.id.asc()).first()

        request_body = {
            'document_id': route_id,
            'lang': route_lang,
            'version_id': route_version_id
        }

        headers = self.add_authorization_header(username='moderator')
        self.app_post_json(
            self._prefix, request_body, status=200, headers=headers)

        response = self.app.get('/routes/' + str(route_id), status=200)
        body = response.json
        self.assertEqual(body['elevation_max'], 1500)
        self.assertEqual(body['activities'], ['skitouring'])
        for locale in body['locales']:
            if locale['lang'] == route_lang:
                self.assertEqual(
                    locale['title'], 'Mont Blanc du ciel')
                self.assertEqual(
                    locale['title_prefix'], 'Mount Everest')

        # Now revert the main waypoint as well and check the title prefix
        # of the route has been updated:
        waypoint_id = self.waypoint2.document_id
        waypoint_lang = 'en'
        # Get version id of the first version of the document:
        waypoint_version_id, = self.session.query(DocumentVersion.id). \
            filter(DocumentVersion.document_id == waypoint_id). \
            filter(DocumentVersion.lang == waypoint_lang). \
            order_by(DocumentVersion.id.asc()).first()

        request_body = {
            'document_id': waypoint_id,
            'lang': waypoint_lang,
            'version_id': waypoint_version_id
        }

        headers = self.add_authorization_header(username='moderator')
        self.app_post_json(
            self._prefix, request_body, status=200, headers=headers)

        response = self.app.get('/routes/' + str(route_id), status=200)
        body = response.json
        for locale in body['locales']:
            if locale['lang'] == route_lang:
                self.assertEqual(
                    locale['title'], 'Mont Blanc du ciel')
                self.assertEqual(
                    locale['title_prefix'], 'Mont Blanc')

    def _add_test_data(self):
        contributor_id = self.global_userids['contributor']

        self.waypoint1 = Waypoint(
            waypoint_type='summit', elevation=2000,
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956 5723604)'),
            locales=[
                WaypointLocale(
                    lang='fr', title='Dent de Crolles',
                    description='...',
                    summary='La Dent de Crolles')
            ])
        self.session.add(self.waypoint1)
        self.waypoint2 = Waypoint(
            waypoint_type='summit', elevation=4810,
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635957 5723605)'),
            locales=[
                WaypointLocale(
                    lang='en', title='Mont Blanc',
                    description='...',
                    summary='The highest point in Europe')
            ])
        self.session.add(self.waypoint2)
        self.waypoint3 = Waypoint(
            waypoint_type='summit', elevation=2432,
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635958 5723606)'),
            locales=[
                WaypointLocale(
                    lang='en', title='Mont de Grange',
                    description='...',
                    summary='Some nice peak')
            ])
        self.session.add(self.waypoint3)
        self.session.flush()

        self.initial_route1_geometry = DocumentGeometry(
            geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723644)',
            geom='SRID=3857;POINT(635961 5723624)'
        )

        self.route1 = Route(
            activities=['skitouring'], elevation_max=1500, elevation_min=700,
            main_waypoint_id=self.waypoint2.document_id,
            geometry=self.initial_route1_geometry,
            locales=[
                RouteLocale(
                    lang='fr', title='Mont Blanc du ciel',
                    description='...', summary='Ski')
            ])
        self.session.add(self.route1)
        self.session.flush()

        DocumentRest.create_new_version(self.waypoint1, contributor_id)
        DocumentRest.create_new_version(self.waypoint2, contributor_id)
        DocumentRest.create_new_version(self.route1, contributor_id)
        update_feed_document_create(self.waypoint1, contributor_id)
        update_feed_document_create(self.waypoint2, contributor_id)
        update_feed_document_create(self.route1, contributor_id)
        self.session.flush()

        association = Association.create(
            parent_document=self.waypoint1,
            child_document=self.route1)
        self.session.add(association)
        self.session.add(association.get_log(contributor_id))
        association = Association.create(
            parent_document=self.waypoint2,
            child_document=self.route1)
        self.session.add(association)
        self.session.add(association.get_log(contributor_id))
        self.session.flush()

        self.waypoint2.elevation = 8848
        for locale in self.waypoint2.locales:
            if locale.lang == 'en':
                locale.title = 'Mount Everest'
                locale.summary = 'The highest point in the world'
        self.waypoint2.geometry.geom = 'SRID=3857;POINT(0 0)'

        self.route1.activities = ['skitouring', 'hiking']
        self.route1.elevation_max = 4500
        self.route1.main_waypoint_id = self.waypoint3.document_id
        for locale in self.route1.locales:
            if locale.lang == 'fr':
                locale.title = 'Some new route name'
        self.route1.geometry.geom = 'SRID=3857;POINT(0 0)'
        self.session.flush()

        DocumentRest.update_version(
            self.waypoint2, contributor_id, 'new version',
            [UpdateType.FIGURES, UpdateType.GEOM, UpdateType.LANG], ['en'])
        DocumentRest.update_version(
            self.route1, contributor_id, 'new version',
            [UpdateType.FIGURES, UpdateType.GEOM, UpdateType.LANG], ['fr'])
        self.session.flush()

        association = Association.create(
            parent_document=self.waypoint3,
            child_document=self.route1)
        self.session.add(association)
        self.session.add(association.get_log(contributor_id))
        self.session.flush()

        # TODO what if former main waypoint is deassociated?
