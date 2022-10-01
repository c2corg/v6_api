from c2corg_api.models.document import UpdateType
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.user import User
from c2corg_api.tests.views import BaseTestRest
from c2corg_api.views.document import DocumentRest
from sqlalchemy.sql.expression import and_


class BaseMaskTest(BaseTestRest):

    def setUp(self):  # noqa
        super(BaseMaskTest, self).setUp()

        self.contributor = self.session.query(User).get(
            self.global_userids['contributor'])
        contributor_id = self.global_userids['contributor']
        self.moderator = self.session.query(User).get(
            self.global_userids['moderator'])

        self.route = Route(activities=['skitouring'], locales=[
            RouteLocale(lang='en', title='Route')
        ])
        self.session.add(self.route)
        self.session.flush()

        DocumentRest.create_new_version(self.route, contributor_id)
        self.session.flush()

        self.route.activities = ['skitouring', 'hiking']
        self.session.flush()

        DocumentRest.update_version(
            self.route, contributor_id, 'new version',
            [UpdateType.FIGURES], [])
        self.session.flush()

    def mask(self, version_id):
        version = self.session.query(DocumentVersion).get(version_id)
        version.masked = True
        self.session.flush()

        self.assertTrue(self.is_masked(version_id))

    def is_masked(self, version_id):
        version = self.session.query(DocumentVersion).get(version_id)
        self.session.refresh(version)
        return version.masked

    def _get_first_version_params(self):
        document_id = self.route.document_id
        lang = 'en'
        first_version_id, = self.session.query(DocumentVersion.id). \
            filter(and_(
                DocumentVersion.document_id == document_id,
                DocumentVersion.lang == lang)). \
            order_by(DocumentVersion.id.asc()).first()
        return {
            'document_id': document_id,
            'lang': lang,
            'version_id': first_version_id
        }

    def _get_version(self, prefix, document_id, lang, version_id, user=None):
        headers = {} if not user else \
            self.add_authorization_header(username=user)
        response = self.app.get(
            '/{}/{}/{}/{}'.format(prefix, document_id, lang, version_id),
            headers=headers,
            status=200)
        self.assertEqual(response.content_type, 'application/json')

        body = response.json
        self.assertIn('document', body)
        self.assertIn('version', body)
        self.assertIn('masked', body['version'])

        return body


class TestVersionMaskRest(BaseMaskTest):

    def setUp(self):  # noqa
        super(TestVersionMaskRest, self).setUp()
        self._prefix = '/versions/mask'

    def test_mask_unauthorized(self):
        self.app_post_json(self._prefix, {}, status=403)

        headers = self.add_authorization_header(username='contributor')
        self.app_post_json(self._prefix, {}, headers=headers, status=403)

    def test_mask_invalid_document_id(self):
        request_body = {
            'document_id': -1,
            'lang': 'en',
            'version_id': 123456
        }

        headers = self.add_authorization_header(username='moderator')
        self.app_post_json(
            self._prefix, request_body, status=400, headers=headers)

    def test_mask_invalid_version_id(self):
        document_id = self.route.document_id
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

    def test_mask_latest_version(self):
        document_id = self.route.document_id
        lang = 'en'
        latest_version_id, = self.session.query(DocumentVersion.id). \
            filter(and_(
                DocumentVersion.document_id == document_id,
                DocumentVersion.lang == lang)). \
            order_by(DocumentVersion.id.desc()).first()
        request_body = {
            'document_id': document_id,
            'lang': lang,
            'version_id': latest_version_id
        }

        headers = self.add_authorization_header(username='moderator')
        response = self.app_post_json(
            self._prefix, request_body, status=400, headers=headers)
        self.assertErrorsContain(
            response.json, 'Bad Request',
            'Version {}/{}/{} is the latest one'.format(
                document_id, lang, latest_version_id))

    def test_mask(self):
        request_body = self._get_first_version_params()
        headers = self.add_authorization_header(username='moderator')
        self.app_post_json(
            self._prefix, request_body, status=200, headers=headers)

        version_id = request_body['version_id']
        self.assertTrue(self.is_masked(version_id))

    def test_not_masked_version(self):
        request_body = self._get_first_version_params()
        document_id, lang, version_id = request_body.values()

        # anonymous
        body = self._get_version('routes', document_id, lang, version_id)
        self.assertFalse(body['version']['masked'])
        self.assertEqual(body['document']['activities'], ['skitouring'])

        # authenticated
        body = self._get_version(
            'routes', document_id, lang, version_id, 'contributor')
        self.assertFalse(body['version']['masked'])
        self.assertIsNotNone(body['document'])
        self.assertEqual(body['document']['activities'], ['skitouring'])

    def test_masked_version(self):
        request_body = self._get_first_version_params()
        document_id, lang, version_id = request_body.values()
        self.mask(version_id)

        # check masked version is referenced in the document history
        body = self.app.get(
            '/document/{}/history/{}'.format(document_id, 'en'), status=200)
        for version in body.json['versions']:
            self.assertEqual(
                version['masked'], version['version_id'] == version_id)

        # anonymous
        body = self._get_version('routes', document_id, lang, version_id)
        self.assertTrue(body['version']['masked'])
        self.assertIsNone(body['document'])

        # authenticated but not moderator
        body = self._get_version(
            'routes', document_id, lang, version_id, 'contributor')
        self.assertTrue(body['version']['masked'])
        self.assertIsNone(body['document'])

        # moderator
        body = self._get_version(
            'routes', document_id, lang, version_id, 'moderator')
        self.assertTrue(body['version']['masked'])
        self.assertIsNotNone(body['document'])
        self.assertEqual(body['document']['activities'], ['skitouring'])

    def test_updated_cache(self):
        request_body = self._get_first_version_params()
        document_id, lang, version_id = request_body.values()

        body = self.app.get(
            '/document/{}/history/{}'.format(document_id, 'en'), status=200)
        self.assertFalse(body.json['versions'][0]['masked'])
        body = self._get_version(
            'routes', document_id, lang, version_id, 'contributor')
        self.assertFalse(body['version']['masked'])

        headers = self.add_authorization_header(username='moderator')
        self.app_post_json(
            self._prefix, request_body, status=200, headers=headers)

        body = self.app.get(
            '/document/{}/history/{}'.format(document_id, 'en'), status=200)
        self.assertTrue(body.json['versions'][0]['masked'])
        body = self._get_version(
            'routes', document_id, lang, version_id, 'contributor')
        self.assertTrue(body['version']['masked'])


class TestVersionUnmaskRest(BaseMaskTest):

    def setUp(self):  # noqa
        super(TestVersionUnmaskRest, self).setUp()
        self._prefix = '/versions/unmask'

    def test_unmask_unauthorized(self):
        self.app_post_json(self._prefix, {}, status=403)

        headers = self.add_authorization_header(username='contributor')
        self.app_post_json(self._prefix, {}, headers=headers, status=403)

    def test_unmask(self):
        request_body = self._get_first_version_params()
        document_id, lang, version_id = request_body.values()

        # first mask a version
        headers = self.add_authorization_header(username='moderator')
        self.app_post_json(
            '/versions/mask', request_body, status=200, headers=headers)
        self.assertTrue(self.is_masked(version_id))

        # then check it's possible to unmask it
        self.app_post_json(
            self._prefix, request_body, status=200, headers=headers)
        self.assertFalse(self.is_masked(version_id))

        body = self._get_version('routes', document_id, lang, version_id)
        self.assertFalse(body['version']['masked'])
        self.assertEqual(body['document']['activities'], ['skitouring'])
