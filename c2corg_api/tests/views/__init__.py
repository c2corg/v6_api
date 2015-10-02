from c2corg_api.tests import BaseTestCase


class BaseTestRest(BaseTestCase):

    def set_prefix_and_model(self, prefix, model):
        self._prefix = prefix
        self._model = model

    def setUp(self):  # noqa
        BaseTestCase.setUp(self)

    def assertMissing(self, error, key):  # noqa
        self.assertEqual(error.get('description'), key + ' is missing')
        self.assertEqual(error.get('name'), key)

    def get_collection(self):
        response = self.app.get(self._prefix, status=200)
        self.assertEqual(response.content_type, 'application/json')

        body = response.json
        self.assertIsInstance(body, list)
        nb_docs = self.session.query(self._model).count()
        self.assertEqual(len(body), nb_docs)
        return body

    def get(self, reference):
        response = self.app.get(self._prefix + '/' +
                                str(reference.document_id),
                                status=200)
        self.assertEqual(response.content_type, 'application/json')

        body = response.json
        self.assertNotIn('id', body)
        self.assertEqual(body.get('document_id'), reference.document_id)
        self.assertIsNotNone(body.get('version_hash'))

        locales = body.get('locales')
        self.assertEqual(len(locales), 2)
        locale_en = locales[0]
        self.assertNotIn('id', locale_en)
        self.assertIsNotNone(locale_en.get('version_hash'))
        self.assertEqual(locale_en.get('culture'), self.locale_en.culture)
        self.assertEqual(locale_en.get('title'), self.locale_en.title)
        return body

    def get_lang(self, reference):
        response = self.app.get(self._prefix + '/' +
                                str(reference.document_id) + '?l=en',
                                status=200)
        self.assertEqual(response.content_type, 'application/json')

        body = response.json
        locales = body.get('locales')
        self.assertEqual(len(locales), 1)
        locale_en = locales[0]
        self.assertEqual(locale_en.get('culture'), self.locale_en.culture)

    def post_error(self, request_body):
        response = self.app.post_json(self._prefix, request_body,
                                      expect_errors=True, status=400)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertGreater(len(errors), 0)
        return body

    def post_missing_title(self, request_body):
        response = self.app.post_json(self._prefix, request_body,
                                      expect_errors=True, status=400)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].get('description'), 'Required')
        self.assertEqual(errors[0].get('name'), 'locales.0.title')
        return body

    def post_non_whitelisted_attribute(self, request_body):
        """`protected` is a non-whitelisted attribute, which is ignored when
        given in a request.
        """
        response = self.app.post_json(self._prefix, request_body, status=200)

        body = response.json
        document_id = body.get('document_id')
        document = self.session.query(self._model).get(document_id)
        # the value for `protected` was ignored
        self.assertFalse(document.protected)
        return (body, document)

    def post_success(self, request_body):
        response = self.app.post_json(self._prefix, request_body, status=200)

        body = response.json
        document_id = body.get('document_id')
        self.assertIsNotNone(body.get('version_hash'))
        self.assertIsNotNone(document_id)

        # check that the version was created correctly
        doc = self.session.query(self._model).get(document_id)
        versions = doc.versions
        self.assertEqual(len(versions), 1)
        version = versions[0]

        culture = body.get('locales')[0].get('culture')
        self.assertEqual(version.culture, culture)

        meta_data = version.history_metadata
        self.assertEqual(meta_data.comment, 'creation')
        self.assertIsNotNone(meta_data.written_at)

        archive_doc = version.document_archive
        self.assertEqual(archive_doc.document_id, document_id)
        self.assertEqual(archive_doc.version_hash, doc.version_hash)

        archive_locale = version.document_locales_archive
        waypoint_locale_en = doc.locales[0]
        self.assertEqual(
            archive_locale.version_hash, waypoint_locale_en.version_hash)
        self.assertEqual(archive_locale.document_id, document_id)
        self.assertEqual(archive_locale.culture, culture)
        return (body, doc)
