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

        locales = body.get('locales')
        self.assertEqual(len(locales), 2)
        locale_en = locales[0]
        self.assertNotIn('id', locale_en)
        self.assertEqual(locale_en.get('culture'), self.locale_en.culture)
        self.assertEqual(locale_en.get('title'), self.locale_en.title)
        return body

    def post_error(self, body):
        response = self.app.post_json(self._prefix, body,
                                      expect_errors=True, status=400)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertGreater(len(errors), 0)
        return body

    def post_success(self, rbody):
        response = self.app.post_json(self._prefix, rbody, status=200)

        body = response.json
        document_id = body.get('document_id')
        self.assertIsNotNone(document_id)

        # check that the version was created correctly
        doc = self.session.query(self._model).get(document_id)
        versions = doc.versions
        self.assertEqual(len(versions), 1)
        version = versions[0]

        culture = body.get('locales')[0].get('culture')
        self.assertEqual(version.culture, culture)
        self.assertEqual(version.version, 1)

        meta_data = version.history_metadata
        self.assertEqual(meta_data.comment, 'creation')
        self.assertIsNotNone(meta_data.written_at)

        archive_doc = version.document_archive
        self.assertEqual(archive_doc.document_id, document_id)

        archive_locale = version.document_locales_archive
        self.assertEqual(archive_locale.document_id, document_id)
        self.assertEqual(archive_locale.culture, culture)
        return (body, doc)
