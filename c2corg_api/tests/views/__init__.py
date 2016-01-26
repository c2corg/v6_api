import json
import urllib.request
import urllib.parse
import urllib.error

from c2corg_api.models.route import Route
from c2corg_api.search import elasticsearch_config
from c2corg_api.search.mapping import SearchDocument
from c2corg_api.tests import BaseTestCase


class BaseTestRest(BaseTestCase):

    def assertErrorsContain(self, body, key):  # noqa
        for error in body['errors']:
            if error.get('name') == key:
                return
        self.fail(str(body) + " does not contain " + key)

    def assertBodyEqual(self, body, key, expected):  # noqa
        self.assertEqual(body.get(key), expected)

    def add_authorization_header(self, username=None, token=None,
                                 headers=None):
        if not headers:
            headers = {}
        if not token:
            token = self.global_tokens[username]
        headers['Authorization'] = 'JWT token="' + token + '"'
        return headers

    def get_json_with_token(self, url, token, status=200):
        headers = self.add_authorization_header(token=token)
        return self.app.get(url, headers=headers, status=status).json

    def get_json_with_contributor(self, url, status=200):
        headers = self.add_authorization_header(username='contributor')
        return self.app.get(url, headers=headers, status=status).json

    def get_json_with_moderator(self, url, status):
        headers = self.add_authorization_header(username='moderator')
        return self.app.get(url, headers=headers, status=status).json

    def assertCorniceMissing(self, error, key):  # noqa
        self.assertEqual(error.get('description'), key + ' is missing')
        self.assertEqual(error.get('name'), key)

    def assertCorniceRequired(self, error, key):  # noqa
        self.assertEqual(error.get('description'), 'Required')
        self.assertEqual(error.get('name'), key)

    def post_json_with_token(self, url, token, body={}, status=200):
        headers = self.add_authorization_header(token=token)
        r = self.app.post_json(url, body, headers=headers, status=status)
        return r.json

    def post_json_with_contributor(self, url, body={}, status=200):
        headers = self.add_authorization_header(username='contributor')
        r = self.app.post_json(url, body, headers=headers, status=status)
        return r.json


class BaseDocumentTestRest(BaseTestRest):

    def set_prefix_and_model(
            self, prefix, model, model_archive, model_archive_locale):
        self._prefix = prefix
        self._model = model
        self._model_archive = model_archive
        self._model_archive_locale = model_archive_locale

    def get_collection(self, params=None):
        prefix = self._prefix
        limit = None
        if params:
            prefix += "?" + urllib.parse.urlencode(params)
            limit = params['limit']

        response = self.app.get(prefix, status=200)
        self.assertEqual(response.content_type, 'application/json')

        body = response.json
        documents = body['documents']
        self.assertIsInstance(documents, list)

        if params is None:
            doc = documents[0]
            available_cultures = doc.get('available_cultures')
            self.assertEqual(sorted(available_cultures), ['en', 'fr'])

        if limit is None:
            nb_docs = self.session.query(self._model).count()
            self.assertEqual(len(documents), nb_docs)
        else:
            self.assertLessEqual(len(documents), limit)

        return body

    def get_collection_lang(self):
        response = self.app.get(self._prefix + '?pl=es', status=200)
        self.assertEqual(response.content_type, 'application/json')

        body = response.json
        documents = body['documents']
        self.assertIsInstance(documents, list)

        doc = documents[0]
        locales = doc.get('locales')
        self.assertEqual(len(locales), 1)
        locale = locales[0]
        self.assertEqual('fr', locale['culture'])

        return body

    def assertResultsEqual(self, actual, expected, total):  # noqa
        actual_docs = actual['documents']
        actual_ids = [json['document_id'] for json in actual_docs]
        self.assertListEqual(actual_ids, expected)
        actual_total = actual['total']
        self.assertEqual(actual_total, total)

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

        available_cultures = body.get('available_cultures')
        self.assertEqual(available_cultures, ['en', 'fr'])
        return body

    def get_version(self, reference, reference_version):
        response = self.app.get(
            '{0}/{1}/en/{2}'.format(
                self._prefix, str(reference.document_id),
                str(reference_version.id)),
            status=200)
        self.assertEqual(response.content_type, 'application/json')

        body = response.json
        self.assertIn('document', body)
        self.assertIn('version', body)
        self.assertIn('previous_version_id', body)
        self.assertIn('next_version_id', body)
        self.assertEqual(
            body['document']['document_id'], reference.document_id)
        self.assertEqual(
            body['version']['version_id'], reference_version.id)
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

    def get_new_lang(self, reference):
        response = self.app.get(self._prefix + '/' +
                                str(reference.document_id) + '?l=it',
                                status=200)
        self.assertEqual(response.content_type, 'application/json')

        body = response.json
        locales = body.get('locales')
        self.assertEqual(len(locales), 0)

    def get_404(self):
        self.app.get(self._prefix + '/-9999', status=404)
        self.app.get(self._prefix + '/-9999?l=es', status=404)

    def post_error(self, request_body):
        response = self.app.post_json(self._prefix, request_body,
                                      expect_errors=True, status=403)

        headers = self.add_authorization_header(username='contributor')
        response = self.app.post_json(self._prefix, request_body,
                                      headers=headers, expect_errors=True,
                                      status=400)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertGreater(len(errors), 0)
        return body

    def post_missing_title(self, request_body):
        response = self.app.post_json(self._prefix, request_body,
                                      expect_errors=True, status=403)

        headers = self.add_authorization_header(username='contributor')
        response = self.app.post_json(self._prefix, request_body,
                                      headers=headers,
                                      expect_errors=True, status=400)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertCorniceRequired(errors[0], 'locales.0.title')
        return body

    def post_missing_geometry(self, request_body):
        response = self.app.post_json(self._prefix, request_body,
                                      expect_errors=True, status=403)

        headers = self.add_authorization_header(username='contributor')
        response = self.app.post_json(
            self._prefix, request_body, headers=headers,
            expect_errors=True, status=400)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertCorniceRequired(errors[0], 'geometry')
        return body

    def post_missing_geom(self, request_body):
        response = self.app.post_json(self._prefix, request_body,
                                      expect_errors=True, status=403)

        headers = self.add_authorization_header(username='contributor')
        response = self.app.post_json(
            self._prefix, request_body, headers=headers,
            expect_errors=True, status=400)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertCorniceRequired(errors[0], 'geometry.geom')
        return body

    def post_missing_locales(self, request_body):
        response = self.app.post_json(self._prefix, request_body,
                                      expect_errors=True, status=403)

        headers = self.add_authorization_header(username='contributor')
        response = self.app.post_json(
            self._prefix, request_body, headers=headers,
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
                                      expect_errors=True, status=403)

        headers = self.add_authorization_header(username='contributor')
        response = self.app.post_json(
            self._prefix, request_body, headers=headers,
            expect_errors=True, status=400)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertEqual(
            errors[0].get('description'), 'culture "en" is given twice')
        self.assertEqual(errors[0].get('name'), 'locales')
        return body

    def post_missing_field(self, request_body, field):
        response = self.app.post_json(self._prefix, request_body,
                                      expect_errors=True, status=403)

        headers = self.add_authorization_header(username='contributor')
        response = self.app.post_json(
            self._prefix, request_body, headers=headers,
            expect_errors=True, status=400)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].get('description'), 'Required')
        self.assertEqual(errors[0].get('name'), field)
        return body

    def post_non_whitelisted_attribute(self, request_body):
        """`protected` is a non-whitelisted attribute, which is ignored when
        given in a request.
        """
        response = self.app.post_json(self._prefix, request_body, status=403)

        headers = self.add_authorization_header(username='contributor')
        response = self.app.post_json(
            self._prefix, request_body, headers=headers, status=200)

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
        response = self.app.post_json(self._prefix, request_body, status=403)

        headers = self.add_authorization_header(username='contributor')
        response = self.app.post_json(self._prefix, request_body,
                                      headers=headers, status=200)

        body = response.json
        document_id = body.get('document_id')
        self.assertIsNotNone(body.get('version'))
        self.assertIsNotNone(document_id)

        # check that the version was created correctly
        doc = self.session.query(self._model).get(document_id)
        self.assertEqual(1, doc.version)
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
        self.assertEqual(1, waypoint_locale_en.version)
        self.assertEqual(
            archive_locale.version, waypoint_locale_en.version)
        self.assertEqual(archive_locale.document_id, document_id)
        self.assertEqual(archive_locale.culture, culture)

        # check updates to the search index
        search_doc = SearchDocument.get(
            id=doc.document_id,
            index=elasticsearch_config['index'])

        self.assertIsNotNone(search_doc['doc_type'])
        self.assertEqual(search_doc['doc_type'], doc.type)

        if isinstance(doc, Route):
            title = waypoint_locale_en.title_prefix + ': ' + \
                waypoint_locale_en.title
            self.assertEqual(search_doc['title_en'], title)
        else:
            self.assertEqual(search_doc['title_en'], waypoint_locale_en.title)

        return (body, doc)

    def put_wrong_document_id(self, request_body):
        response = self.app.put_json(
            self._prefix + '/-9999', request_body, status=403)

        headers = self.add_authorization_header(username='contributor')
        response = self.app.put_json(
            self._prefix + '/-9999', request_body, headers=headers, status=404)

        body = response.json
        self.assertEqual(body['status'], 'error')
        self.assertEqual(body['errors'][0]['name'], 'Not Found')

    def put_wrong_version(self, request_body, id):
        response = self.app.put_json(
            self._prefix + '/' + str(id), request_body, status=403)

        headers = self.add_authorization_header(username='contributor')
        response = self.app.put_json(
            self._prefix + '/' + str(id), request_body, headers=headers,
            status=409)

        body = response.json
        self.assertEqual(body['status'], 'error')
        self.assertEqual(body['errors'][0]['name'], 'Conflict')

    def put_wrong_ids(self, request_body, id):
        """The id given in the URL does not equal the document_id in the
        request body.
        """
        response = self.app.put_json(
            self._prefix + '/' + str(id + 1), request_body, status=403)

        headers = self.add_authorization_header(username='contributor')
        response = self.app.put_json(
            self._prefix + '/' + str(id + 1), request_body, headers=headers,
            status=400)
        body = response.json
        self.assertEqual(body['status'], 'error')
        self.assertEqual(body['errors'][0]['name'], 'Bad Request')

    def put_put_no_document(self, id):
        request_body = {
            'message': '...'
        }
        response = self.app.put_json(
            self._prefix + '/' + str(id), request_body, status=403)

        headers = self.add_authorization_header(username='contributor')
        response = self.app.put_json(
            self._prefix + '/' + str(id), request_body, headers=headers,
            status=400)

        body = response.json
        self.assertEqual(body['status'], 'error')
        self.assertEqual(
            body['errors'][0]['description'], 'document is missing')

    def put_missing_field(self, request_body, document, field):
        response = self.app.put_json(
            self._prefix + '/' + str(document.document_id), request_body,
            status=403)

        headers = self.add_authorization_header(username='contributor')
        response = self.app.put_json(
            self._prefix + '/' + str(document.document_id), request_body,
            headers=headers, status=400)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertCorniceRequired(errors[0], field)

    def put_success_all(self, request_body, document):
        """Test updating a document with changes to the figures and locales.
        """
        response = self.app.put_json(
            self._prefix + '/' + str(document.document_id), request_body,
            status=403)

        headers = self.add_authorization_header(username='contributor')
        response = self.app.put_json(
            self._prefix + '/' + str(document.document_id), request_body,
            headers=headers, status=200)

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

        archive_locale_fr = version_fr.document_locales_archive
        self.assertEqual(archive_locale_fr.document_id, document_id)
        self.assertEqual(
            archive_locale_fr.version, self.locale_fr.version)
        self.assertEqual(archive_locale_fr.culture, 'fr')

        # check updates to the search index
        search_doc = SearchDocument.get(
            id=document.document_id,
            index=elasticsearch_config['index'])

        self.assertEqual(search_doc['doc_type'], document.type)
        self.assertEqual(search_doc['title_en'], archive_locale.title)
        self.assertEqual(search_doc['title_fr'], archive_locale_fr.title)

        return (body, document)

    def put_success_figures_only(self, request_body, document):
        """Test updating a document with changes to the figures only.
        """
        response = self.app.put_json(
            self._prefix + '/' + str(document.document_id), request_body,
            status=403)

        headers = self.add_authorization_header(username='contributor')
        response = self.app.put_json(
            self._prefix + '/' + str(document.document_id), request_body,
            headers=headers, status=200)

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

        # check updates to the search index
        search_doc = SearchDocument.get(
            id=document.document_id,
            index=elasticsearch_config['index'])

        self.assertEqual(search_doc['doc_type'], document.type)

        if isinstance(document, Route) and document.main_waypoint_id:
            locale_en = document.get_locale('en')
            title = locale_en.title_prefix + ': ' + locale_en.title
            self.assertEqual(search_doc['title_en'], title)

            locale_fr = document.get_locale('fr')
            title = locale_fr.title_prefix + ' : ' + locale_fr.title
            self.assertEqual(search_doc['title_fr'], title)
        else:
            self.assertEqual(
                search_doc['title_en'], document.get_locale('en').title)
            self.assertEqual(
                search_doc['title_fr'], document.get_locale('fr').title)

        return (body, document)

    def put_success_lang_only(self, request_body, document):
        """Test updating a document with only changes to a locale.
        """
        response = self.app.put_json(
            self._prefix + '/' + str(document.document_id), request_body,
            status=403)

        headers = self.add_authorization_header(username='contributor')
        response = self.app.put_json(
            self._prefix + '/' + str(document.document_id), request_body,
            headers=headers, status=200)

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

        # check updates to the search index
        search_doc = SearchDocument.get(
            id=document.document_id,
            index=elasticsearch_config['index'])

        self.assertEqual(search_doc['doc_type'], document.type)
        self.assertEqual(
            search_doc['title_en'], document.get_locale('en').title)
        self.assertEqual(
            search_doc['title_fr'], document.get_locale('fr').title)

        return (body, document)

    def put_success_new_lang(self, request_body, document):
        """Test updating a document by adding a new locale.
        """
        response = self.app.put_json(
            self._prefix + '/' + str(document.document_id), request_body,
            status=403)

        headers = self.add_authorization_header(username='contributor')
        response = self.app.put_json(
            self._prefix + '/' + str(document.document_id), request_body,
            headers=headers, status=200)

        headers = self.add_authorization_header(username='contributor')
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

        # check updates to the search index
        search_doc = SearchDocument.get(
            id=document.document_id,
            index=elasticsearch_config['index'])

        self.assertEqual(search_doc['doc_type'], document.type)
        self.assertEqual(
            search_doc['title_en'], document.get_locale('en').title)
        self.assertEqual(
            search_doc['title_fr'], document.get_locale('fr').title)
        self.assertEqual(
            search_doc['title_es'], document.get_locale('es').title)

        return (body, document)
