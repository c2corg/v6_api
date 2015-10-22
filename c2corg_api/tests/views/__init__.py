import json

from c2corg_api.tests import BaseTestCase


class BaseTestRest(BaseTestCase):

    def set_prefix_and_model(
            self, prefix, model, model_archive, model_archive_locale):
        self._prefix = prefix
        self._model = model
        self._model_archive = model_archive
        self._model_archive_locale = model_archive_locale

    def setUp(self):  # noqa
        BaseTestCase.setUp(self)

    def assertMissing(self, error, key):  # noqa
        self.assertEqual(error.get('description'), key + ' is missing')
        self.assertEqual(error.get('name'), key)

    def assertRequired(self, error, key):  # noqa
        self.assertEqual(error.get('description'), 'Required')
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
        self.assertIsNotNone(body.get('version'))

        locales = body.get('locales')
        self.assertEqual(len(locales), 2)
        locale_en = locales[0]
        self.assertNotIn('id', locale_en)
        self.assertIsNotNone(locale_en.get('version'))
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
        self.assertRequired(errors[0], 'locales.0.title')
        return body

    def post_missing_geometry(self, request_body):
        response = self.app.post_json(self._prefix, request_body,
                                      expect_errors=True, status=400)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertRequired(errors[0], 'geometry')
        return body

    def post_missing_geom(self, request_body):
        response = self.app.post_json(self._prefix, request_body,
                                      expect_errors=True, status=400)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertRequired(errors[0], 'geometry.geom')
        return body

    def post_missing_locales(self, request_body):
        response = self.app.post_json(self._prefix, request_body,
                                      expect_errors=True, status=400)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].get('description'), 'Required')
        self.assertEqual(errors[0].get('name'), 'locales')
        return body

    def post_same_locale_twice(self, request_body):
        response = self.app.post_json(self._prefix, request_body,
                                      expect_errors=True, status=400)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertEqual(
            errors[0].get('description'), 'culture "en" is given twice')
        self.assertEqual(errors[0].get('name'), 'locales')
        return body

    def post_missing_elevation(self, request_body):
        response = self.app.post_json(self._prefix, request_body,
                                      expect_errors=True, status=400)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].get('description'), 'Required')
        self.assertEqual(errors[0].get('name'), 'elevation')
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

    def post_missing_content_type(self, request_body):
        response = self.app.post(
            self._prefix, params=json.dumps(request_body), status=415)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].get('location'), 'header')
        self.assertEqual(errors[0].get('name'), 'Content-Type')
        return body

    def post_success(self, request_body):
        response = self.app.post_json(self._prefix, request_body, status=200)

        body = response.json
        document_id = body.get('document_id')
        self.assertIsNotNone(body.get('version'))
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
        self.assertEqual(archive_doc.version, doc.version)

        archive_locale = version.document_locales_archive
        waypoint_locale_en = doc.locales[0]
        self.assertEqual(
            archive_locale.version, waypoint_locale_en.version)
        self.assertEqual(archive_locale.document_id, document_id)
        self.assertEqual(archive_locale.culture, culture)
        return (body, doc)

    def put_wrong_document_id(self, request_body):
        response = self.app.put_json(
            self._prefix + '/-9999', request_body, status=404)
        body = response.json
        self.assertEqual(body['status'], 'error')
        self.assertEqual(body['errors'][0]['name'], 'Not Found')

    def put_wrong_version(self, request_body, id):
        response = self.app.put_json(
            self._prefix + '/' + str(id), request_body, status=409)
        body = response.json
        self.assertEqual(body['status'], 'error')
        self.assertEqual(body['errors'][0]['name'], 'Conflict')

    def put_wrong_ids(self, request_body, id):
        """The id given in the URL does not equal the document_id in the
        request body.
        """
        response = self.app.put_json(
            self._prefix + '/' + str(id + 1), request_body, status=400)
        body = response.json
        self.assertEqual(body['status'], 'error')
        self.assertEqual(body['errors'][0]['name'], 'Bad Request')

    def put_put_no_document(self, id):
        request_body = {
            'message': '...'
        }
        response = self.app.put_json(
            self._prefix + '/' + str(id), request_body, status=400)
        body = response.json
        self.assertEqual(body['status'], 'error')
        self.assertEqual(
            body['errors'][0]['description'], 'document is missing')

    def put_missing_elevation(self, request_body, document):
        response = self.app.put_json(
            self._prefix + '/' + str(document.document_id), request_body,
            status=400)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertRequired(errors[0], 'elevation')

    def put_success_all(self, request_body, document):
        """Test updating a document with changes to the figures and locales.
        """
        response = self.app.put_json(
            self._prefix + '/' + str(document.document_id), request_body)

        body = response.json
        document_id = body.get('document_id')
        self.assertNotEquals(
            body.get('version'), document.version)
        self.assertEquals(body.get('document_id'), document_id)

        # check that the document was updated correctly
        self.session.expire_all()
        document = self.session.query(self._model).get(document_id)
        self.assertEquals(len(document.locales), 2)
        locale_en = document.get_locale('en')

        # check that a new archive_document was created
        archive_count = self.session.query(self._model_archive). \
            filter(
                getattr(self._model_archive, 'document_id') == document_id). \
            count()
        self.assertEqual(archive_count, 2)

        # check that only one new archive_document_locale was created (only
        # for 'en' not 'fr')
        archive_locale_count = \
            self.session.query(self._model_archive_locale). \
            filter(
                document_id == getattr(
                    self._model_archive_locale, 'document_id')
            ). \
            count()
        self.assertEqual(archive_locale_count, 3)

        # check that new versions were created
        versions = document.versions
        self.assertEqual(len(versions), 4)

        # version with culture 'en'
        version_en = versions[2]

        self.assertEqual(version_en.culture, 'en')

        meta_data_en = version_en.history_metadata
        self.assertEqual(meta_data_en.comment, 'Update')
        self.assertIsNotNone(meta_data_en.written_at)

        archive_document_en = version_en.document_archive
        self.assertEqual(archive_document_en.document_id, document_id)
        self.assertEqual(
            archive_document_en.version, document.version)

        archive_locale = version_en.document_locales_archive
        self.assertEqual(archive_locale.document_id, document_id)
        self.assertEqual(archive_locale.version, locale_en.version)
        self.assertEqual(archive_locale.culture, 'en')

        # version with culture 'fr'
        version_fr = versions[3]

        self.assertEqual(version_fr.culture, 'fr')

        meta_data_fr = version_fr.history_metadata
        self.assertIs(meta_data_en, meta_data_fr)

        archive_document_fr = version_fr.document_archive
        self.assertIs(archive_document_en, archive_document_fr)

        archive_locale = version_fr.document_locales_archive
        self.assertEqual(archive_locale.document_id, document_id)
        self.assertEqual(
            archive_locale.version, self.locale_fr.version)
        self.assertEqual(archive_locale.culture, 'fr')

        return (body, document)

    def put_success_figures_only(self, request_body, document):
        """Test updating a document with changes to the figures and locales.
        """
        response = self.app.put_json(
            self._prefix + '/' + str(document.document_id), request_body)

        body = response.json
        document_id = body.get('document_id')
        self.assertNotEquals(
            body.get('version'), document.version)
        self.assertEquals(body.get('document_id'), document_id)

        # check that the document was updated correctly
        self.session.expire_all()
        document = self.session.query(self._model).get(document_id)
        self.assertEquals(len(document.locales), 2)

        # check that a new archive_document was created
        archive_count = self.session.query(self._model_archive). \
            filter(
                getattr(self._model_archive, 'document_id') == document_id). \
            count()
        self.assertEqual(archive_count, 2)

        # check that no new archive_document_locale was created
        archive_locale_count = \
            self.session.query(self._model_archive_locale). \
            filter(
                document_id == getattr(
                    self._model_archive_locale, 'document_id')
            ). \
            count()
        self.assertEqual(archive_locale_count, 2)

        # check that new versions were created
        versions = document.versions
        self.assertEqual(len(versions), 4)

        # version with culture 'en'
        version_en = versions[2]

        self.assertEqual(version_en.culture, 'en')

        meta_data_en = version_en.history_metadata
        self.assertEqual(meta_data_en.comment, 'Changing figures')
        self.assertIsNotNone(meta_data_en.written_at)

        # version with culture 'fr'
        version_fr = versions[3]

        self.assertEqual(version_fr.culture, 'fr')

        meta_data_fr = version_fr.history_metadata
        self.assertIs(meta_data_en, meta_data_fr)

        archive_document_en = version_en.document_archive
        archive_document_fr = version_fr.document_archive
        self.assertIs(archive_document_en, archive_document_fr)

        return (body, document)

    def put_success_lang_only(self, request_body, document):
        """Test updating a document with only changes to a locale.
        """
        response = self.app.put_json(
            self._prefix + '/' + str(document.document_id), request_body)

        body = response.json
        document_id = body.get('document_id')
        # document version does not change!
        self.assertEquals(body.get('version'), document.version)
        self.assertEquals(body.get('document_id'), document_id)

        # check that the document was updated correctly
        self.session.expire_all()
        document = self.session.query(self._model).get(document_id)
        self.assertEquals(len(document.locales), 2)

        # check that no new archive_document was created
        archive_count = self.session.query(self._model_archive). \
            filter(
                getattr(self._model_archive, 'document_id') == document_id). \
            count()
        self.assertEqual(archive_count, 1)

        # check that one new archive_document_locale was created
        archive_locale_count = \
            self.session.query(self._model_archive_locale). \
            filter(
                document_id == getattr(
                    self._model_archive_locale, 'document_id')
            ). \
            count()
        self.assertEqual(archive_locale_count, 3)

        # check that one new version was created
        versions = document.versions
        self.assertEqual(len(versions), 3)

        # version with culture 'en'
        version_en = versions[2]

        self.assertEqual(version_en.culture, 'en')

        meta_data_en = version_en.history_metadata
        self.assertEqual(meta_data_en.comment, 'Changing lang')
        self.assertIsNotNone(meta_data_en.written_at)

        # version with culture 'fr'
        version_fr = versions[1]

        self.assertEqual(version_fr.culture, 'fr')

        meta_data_fr = version_fr.history_metadata
        self.assertIsNot(meta_data_en, meta_data_fr)

        archive_waypoint_en = version_en.document_archive
        archive_waypoint_fr = version_fr.document_archive
        self.assertIs(archive_waypoint_en, archive_waypoint_fr)

        return (body, document)

    def put_success_new_lang(self, request_body, document):
        """Test updating a document by adding a new locale.
        """
        response = self.app.put_json(
            self._prefix + '/' + str(document.document_id), request_body)

        body = response.json
        document_id = body.get('document_id')
        # document version does not change!
        self.assertEquals(body.get('version'), document.version)
        self.assertEquals(body.get('document_id'), document_id)

        # check that the document was updated correctly
        self.session.expire_all()
        document = self.session.query(self._model).get(document_id)
        self.assertEquals(len(document.locales), 3)

        # check that no new archive_document was created
        archive_count = self.session.query(self._model_archive). \
            filter(
                getattr(self._model_archive, 'document_id') == document_id). \
            count()
        self.assertEqual(archive_count, 1)

        # check that one new archive_document_locale was created
        archive_locale_count = \
            self.session.query(self._model_archive_locale). \
            filter(
                document_id == getattr(
                    self._model_archive_locale, 'document_id')
            ). \
            count()
        self.assertEqual(archive_locale_count, 3)

        # check that one new version was created
        versions = document.versions
        self.assertEqual(len(versions), 3)

        # version with culture 'en'
        version_en = versions[0]

        self.assertEqual(version_en.culture, 'en')

        meta_data_en = version_en.history_metadata

        # version with culture 'fr'
        version_fr = versions[1]

        self.assertEqual(version_fr.culture, 'fr')

        meta_data_fr = version_fr.history_metadata
        self.assertIs(meta_data_en, meta_data_fr)

        archive_document_en = version_en.document_archive
        archive_document_fr = version_fr.document_archive
        self.assertIs(archive_document_en, archive_document_fr)

        # version with culture 'es'
        version_es = versions[2]

        self.assertEqual(version_es.culture, 'es')

        meta_data_es = version_es.history_metadata
        self.assertIsNot(meta_data_en, meta_data_es)

        archive_document_es = version_es.document_archive
        self.assertIs(archive_document_es, archive_document_fr)

        return (body, document)
