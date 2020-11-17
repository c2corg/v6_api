import json
import urllib.request
import urllib.parse
import urllib.error

from c2corg_api.caching import cache_document_detail
from c2corg_api.models.cache_version import CacheVersion, get_cache_key
from c2corg_api.models.feed import DocumentChange
from c2corg_api.models.route import Route
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import UserProfile, USERPROFILE_TYPE
from c2corg_api.scripts.es.sync import sync_es
from c2corg_api.search import elasticsearch_config, search_documents
from c2corg_api.tests import BaseTestCase
from dateutil import parser as datetime_parser
from dogpile.cache.api import NO_VALUE


class BaseTestRest(BaseTestCase):

    def assertErrorsContain(self, body, key, value=None):  # noqa
        for error in body['errors']:
            if error.get('name') == key:
                if value is not None:
                    self.assertEqual(error.get('description'), value)
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

    def assertCorniceNotInEnum(self, error, key):  # noqa
        self.assertIn('is not one of', error.get('description'))
        self.assertEqual(error.get('name'), key)

    def assertCorniceRequired(self, error, key):  # noqa
        self.assertEqual(error.get('description'), 'Required')
        self.assertEqual(error.get('name'), key)

    def assertError(self, errors, name, description):  # noqa
        for error in errors:
            if description == error.get('description') and \
                    name == error.get('name'):
                return
        self.fail('no error ({}, {}) in {}'.format(name, description, errors))

    def get_error(self, errors, name):  # noqa
        for error in errors:
            if name == error.get('name'):
                return error
        self.fail('no error for {0}'.format(name))

    def post_json_with_token(self, url, token, body={}, status=200):
        headers = self.add_authorization_header(token=token)
        r = self.app_post_json(url, body, headers=headers, status=status)
        return r.json

    def post_json_with_contributor(self, url, body={}, status=200,
                                   username='contributor', headers={}):
        headers = self.add_authorization_header(username=username,
                                                headers=headers)
        r = self.app_post_json(url, body, headers=headers, status=status)
        return r.json

    def assertNotifiedEs(self):  # noqa
        queue = self.queue_config.queue(self.queue_config.connection)
        self.assertIsNotNone(queue.get(), 'no sync. notification sent for ES')

    def assertNotNotifiedEs(self):  # noqa
        queue = self.queue_config.queue(self.queue_config.connection)
        self.assertIsNone(
            queue.get(), 'unexpected sync. notification sent for ES')

    def sync_es(self):
        self.assertNotifiedEs()
        sync_es(self.session)

    def get_latest_version(self, lang, versions):
        versions_in_lang = [v for v in versions if v.lang == lang]
        versions_in_lang.sort(key=lambda v: v.id, reverse=True)
        return versions_in_lang[0]

    def get_locale(self, lang, locales):
        return next(
            filter(lambda locale: locale['lang'] == lang, locales),
            None)

    def check_cache_version(self, document_id, version):
        cache_version = self.session.query(CacheVersion).get(document_id)
        self.assertIsNotNone(cache_version)
        self.assertEqual(cache_version.version, version)

    def get_feed_change(self, document_id, change_type=None):
        q = self.session.query(DocumentChange). \
            filter(DocumentChange.document_id == document_id)

        if change_type:
            q = q.filter(DocumentChange.change_type == change_type)

        return q.first()


class BaseDocumentTestRest(BaseTestRest):

    def set_prefix_and_model(
            self, prefix, doc_type, model,
            model_archive, model_archive_locale):
        self._prefix = prefix
        self._doc_type = doc_type
        self._model = model
        self._model_archive = model_archive
        self._model_archive_locale = model_archive_locale

    def get_collection(self, params=None, user=None):
        prefix = self._prefix
        limit = None
        if params:
            prefix += "?" + urllib.parse.urlencode(params)
            limit = params['limit']

        headers = {} if not user else \
            self.add_authorization_header(username=user)

        response = self.app.get(prefix, headers=headers, status=200)
        self.assertEqual(response.content_type, 'application/json')

        body = response.json
        documents = body['documents']
        self.assertIsInstance(documents, list)

        if params is None:
            doc = documents[0]
            available_langs = doc.get('available_langs')
            self.assertEqual(sorted(available_langs), ['en', 'fr'])
            self.assertIn('protected', doc)
            self.assertIn('type', doc)

        if limit is None:
            if self._model == UserProfile:
                nb_docs = self.session.query(UserProfile). \
                    join(User). \
                    filter(User.email_validated). \
                    filter(UserProfile.redirects_to.is_(None)).count()
            else:
                nb_docs = self.session.query(self._model). \
                    filter(getattr(self._model, 'redirects_to').is_(None)).\
                    count()
            self.assertEqual(len(documents), nb_docs)
        else:
            self.assertLessEqual(len(documents), limit)

        return body

    def get_collection_search(self, params=None, user=None):
        prefix = self._prefix
        if params:
            prefix += "?" + urllib.parse.urlencode(params)

        headers = {} if not user else \
            self.add_authorization_header(username=user)

        response = self.app.get(prefix, headers=headers, status=200)
        self.assertEqual(response.content_type, 'application/json')

        return response.json

    def get_collection_lang(self, user=None):
        headers = {} if not user else \
            self.add_authorization_header(username=user)

        response = self.app.get(
            self._prefix + '?pl=es', headers=headers, status=200)
        self.assertEqual(response.content_type, 'application/json')

        body = response.json
        documents = body['documents']
        self.assertIsInstance(documents, list)

        doc = documents[0]
        locales = doc.get('locales')
        self.assertEqual(len(locales), 1)
        locale = locales[0]
        self.assertEqual('fr', locale['lang'])
        self.assertIn('protected', doc)
        self.assertIn('type', doc)

        return body

    def assertResultsEqual(self, actual, expected, total):  # noqa
        actual_docs = actual['documents']
        actual_ids = [json['document_id'] for json in actual_docs]
        self.assertListEqual(actual_ids, expected)
        actual_total = actual['total']
        self.assertEqual(actual_total, total)

    def get(self, reference, user=None, check_title=True, ignore_checks=False):
        headers = {} if not user else \
            self.add_authorization_header(username=user)
        response = self.app.get(self._prefix + '/' +
                                str(reference.document_id),
                                headers=headers,
                                status=200)
        self.assertEqual(response.content_type, 'application/json')

        body = response.json
        self.assertNotIn('id', body)
        self.assertEqual(body.get('document_id'), reference.document_id)
        self.assertIsNotNone(body.get('version'))
        self.assertIn('type', body)
        self.assertIsNotNone(body.get('associations'))

        locales = body.get('locales')
        if ignore_checks is False:
            self.assertEqual(len(locales), 2)
        locale_en = get_locale(locales, 'en')
        self.assertNotIn('id', locale_en)
        self.assertIsNotNone(locale_en.get('version'))
        self.assertEqual(locale_en.get('lang'), self.locale_en.lang)
        if check_title:
            self.assertEqual(locale_en.get('title'), self.locale_en.title)

        available_langs = body.get('available_langs')
        if ignore_checks is False:
            self.assertCountEqual(available_langs, ['en', 'fr'])
        return body

    def get_caching(self, reference, user=None):
        headers = {} if not user else \
            self.add_authorization_header(username=user)

        url = '{0}/{1}'.format(self._prefix, str(reference.document_id))
        cache_key = get_cache_key(
            reference.document_id,
            None,
            document_type=self._doc_type)

        cache_value = cache_document_detail.get(cache_key)

        self.assertEqual(cache_value, NO_VALUE)

        # check that the response is cached
        self.app.get(url, headers=headers, status=200)

        cache_value = cache_document_detail.get(cache_key)
        self.assertNotEqual(cache_value, NO_VALUE)

        # check that values are returned from the cache
        fake_cache_value = {'document': 'fake doc'}
        cache_document_detail.set(cache_key, fake_cache_value)

        response = self.app.get(url, headers=headers, status=200)
        body = response.json
        self.assertEqual(body, fake_cache_value)

        # check that cache handles document types
        prefix = "/routes" if self._prefix != "/routes" else "/waypoint"
        url = '{0}/{1}'.format(prefix, str(reference.document_id))
        self.app.get(url, headers=headers, status=404)

    def get_version(self, reference, reference_version, user=None):
        headers = {} if not user else \
            self.add_authorization_header(username=user)
        response = self.app.get(
            '{0}/{1}/en/{2}'.format(
                self._prefix, str(reference.document_id),
                str(reference_version.id)),
            headers=headers,
            status=200)
        self.assertEqual(response.content_type, 'application/json')

        body = response.json
        self.assertIn('document', body)

        self.assertIn('cooked', body['document'])
        self.assertIn('lang', body['document']['cooked'])
        self.assertEqual(body['document']['cooked']['lang'], 'en')

        self.assertIn('version', body)
        self.assertIn('previous_version_id', body)
        self.assertIn('next_version_id', body)
        self.assertEqual(
            body['document']['document_id'], reference.document_id)
        self.assertEqual(
            body['version']['version_id'], reference_version.id)

        version = body['version']
        written_at = version['written_at']
        time = datetime_parser.parse(written_at)
        self.assertIsNotNone(time.tzinfo)

        return body

    def get_info(self, reference, lang):
        response = self.app.get(
            '{0}/{1}/{2}/info'.format(
                self._prefix, str(reference.document_id),
                lang),
            status=200)
        self.assertEqual(response.content_type, 'application/json')

        body = response.json
        self.assertIn('document_id', body)
        self.assertIn('locales', body)
        self.assertEqual(
            body['document_id'], reference.document_id)
        self.assertEqual(len(body['locales']), 1)
        locale = body['locales'][0]
        self.assertIn('lang', locale)
        self.assertIn('title_prefix', locale)
        self.assertIn('title', locale)
        return body, locale

    def get_info_404(self):
        self.app.get(self._prefix + '/9999999/en/info', status=404)

    def _get_cooked(self, reference, lang, user=None):
        headers = {} if not user else \
            self.add_authorization_header(username=user)

        response = self.app.get(self._prefix + '/' +
                                str(reference.document_id) + '?cook=' + lang,
                                headers=headers,
                                status=200)
        self.assertEqual(response.content_type, 'application/json')

        body = response.json
        self.assertIn('cooked', body)
        self.assertIn('locales', body)

        locales = body.get('locales')
        cooked = body.get('cooked')

        self.assertEqual(len(locales), 1)

        return body, locales[0], cooked

    def get_cooked(self, reference, user=None):
        body, locale, cooked = self._get_cooked(reference, "en", user)

        self.assertEqual(locale.get('lang'), self.locale_en.lang)
        self.assertEqual(locale.get('lang'), "en")
        self.assertEqual(cooked.get('lang'), "en")

        return body

    def get_cooked_with_defaulting(self, reference, user=None):
        body, locale, cooked = self._get_cooked(reference, "it", user)

        self.assertEqual(locale.get('lang'), "fr")
        self.assertEqual(cooked.get('lang'), "fr")

        return body

    def get_lang(self, reference, user=None):
        headers = {} if not user else \
            self.add_authorization_header(username=user)

        response = self.app.get(self._prefix + '/' +
                                str(reference.document_id) + '?l=en',
                                headers=headers,
                                status=200)
        self.assertEqual(response.content_type, 'application/json')

        body = response.json
        locales = body.get('locales')
        self.assertEqual(len(locales), 1)
        locale_en = locales[0]
        self.assertEqual(locale_en.get('lang'), self.locale_en.lang)
        self.assertIn('protected', body)
        self.assertIn('topic_id', locale_en)
        return body

    def get_new_lang(self, reference, user=None):
        headers = {} if not user else \
            self.add_authorization_header(username=user)

        response = self.app.get(self._prefix + '/' +
                                str(reference.document_id) + '?l=it',
                                headers=headers,
                                status=200)
        self.assertEqual(response.content_type, 'application/json')

        body = response.json
        locales = body.get('locales')
        self.assertEqual(len(locales), 0)

    def get_404(self, user=None):
        headers = {} if not user else \
            self.add_authorization_header(username=user)

        self.app.get(
            self._prefix + '/9999999', headers=headers, status=404)
        self.app.get(
            self._prefix + '/9999999?l=es', headers=headers, status=404)

    def post_error(self, request_body, user='contributor'):
        response = self.app_post_json(self._prefix, request_body,
                                      expect_errors=True, status=403)

        headers = self.add_authorization_header(username=user)
        response = self.app_post_json(self._prefix, request_body,
                                      headers=headers, expect_errors=True,
                                      status=400)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertGreater(len(errors), 0)
        return body

    def post_missing_title(self, request_body, user='contributor', prefix=''):
        response = self.app_post_json(self._prefix, request_body,
                                      expect_errors=True, status=403)

        headers = self.add_authorization_header(username=user)
        response = self.app_post_json(self._prefix, request_body,
                                      headers=headers,
                                      expect_errors=True, status=400)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertCorniceRequired(errors[0], prefix + 'locales.0.title')
        return body

    def post_missing_geometry(self, request_body):
        response = self.app_post_json(self._prefix, request_body,
                                      expect_errors=True, status=403)

        headers = self.add_authorization_header(username='contributor')
        response = self.app_post_json(
            self._prefix, request_body, headers=headers,
            expect_errors=True, status=400)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertCorniceRequired(errors[0], 'geometry')
        return body

    def post_missing_geom(self, request_body):
        response = self.app_post_json(self._prefix, request_body,
                                      expect_errors=True, status=403)

        headers = self.add_authorization_header(username='contributor')
        response = self.app_post_json(
            self._prefix, request_body, headers=headers,
            expect_errors=True, status=400)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertCorniceRequired(errors[0], 'geometry.geom')
        return body

    def post_wrong_geom_type(self, request_body):
        response = self.app_post_json(self._prefix, request_body,
                                      expect_errors=True, status=403)

        headers = self.add_authorization_header(username='contributor')
        response = self.app_post_json(
            self._prefix, request_body, headers=headers,
            expect_errors=True, status=400)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        return errors

    def post_missing_locales(self, request_body):
        response = self.app_post_json(self._prefix, request_body,
                                      expect_errors=True, status=403)

        headers = self.add_authorization_header(username='contributor')
        response = self.app_post_json(
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
        response = self.app_post_json(self._prefix, request_body,
                                      expect_errors=True, status=403)

        headers = self.add_authorization_header(username='contributor')
        response = self.app_post_json(
            self._prefix, request_body, headers=headers,
            expect_errors=True, status=400)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertEqual(
            errors[0].get('description'), 'lang "en" is given twice')
        self.assertEqual(errors[0].get('name'), 'locales')
        return body

    def post_missing_field(self, request_body, field):
        response = self.app_post_json(self._prefix, request_body,
                                      expect_errors=True, status=403)

        headers = self.add_authorization_header(username='contributor')
        response = self.app_post_json(
            self._prefix, request_body, headers=headers,
            expect_errors=True, status=400)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].get('description'), 'Required')
        self.assertEqual(errors[0].get('name'), field)
        return body

    def post_non_whitelisted_attribute(self, request_body, user='contributor'):
        """`protected` is a non-whitelisted attribute, which is ignored when
        given in a request.
        """
        response = self.app_post_json(self._prefix, request_body, status=403)

        headers = self.add_authorization_header(username=user)
        response = self.app_post_json(
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

    def post_success(self, request_body, user='contributor',
                     validate_with_auth=False, skip_validation=False):
        response = self.app_post_json(self._prefix, request_body, status=403)

        headers = self.add_authorization_header(username=user)
        response = self.app_post_json(self._prefix, request_body,
                                      headers=headers, status=200)

        body = response.json
        if skip_validation:
            document_id = body.get('document_id')
            response = self.app.get(
                self._prefix + '/' + str(document_id), status=200)
            doc = self.session.query(self._model).get(document_id)
            return response.json, doc
        else:
            return self._validate_document(body, headers, validate_with_auth)

    def _validate_document(self, body, headers=None, validate_with_auth=False):
        document_id = body.get('document_id')
        self.assertIsNotNone(document_id)

        if validate_with_auth:
            response = self.app.get(self._prefix + '/' + str(document_id),
                                    headers=headers, status=200)
        else:
            response = self.app.get(self._prefix + '/' + str(document_id),
                                    status=200)
        self.assertEqual(response.content_type, 'application/json')

        body = response.json
        self.assertIsNotNone(body.get('version'))
        self.assertEqual(body.get('protected'), False)

        # check that the version was created correctly
        doc = self.session.query(self._model).get(document_id)
        self.assertEqual(1, doc.version)
        versions = doc.versions
        self.assertEqual(len(versions), 1)
        version = versions[0]

        lang = body.get('locales')[0].get('lang')
        self.assertEqual(version.lang, lang)

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
        self.assertEqual(archive_locale.lang, lang)

        # check updates to the search index
        self.sync_es()
        search_doc = search_documents[self._doc_type].get(
            id=doc.document_id,
            index=elasticsearch_config['index'])

        self.assertIsNotNone(search_doc['doc_type'])
        self.assertEqual(search_doc['doc_type'], doc.type)

        if isinstance(doc, Route):
            title = waypoint_locale_en.title_prefix + ' : ' + \
                waypoint_locale_en.title
            self.assertEqual(search_doc['title_en'], title)
        else:
            self.assertEqual(search_doc['title_en'], waypoint_locale_en.title)

        cache_version = self.session.query(CacheVersion).get(document_id)
        self.assertIsNotNone(cache_version)
        self.assertEqual(cache_version.version, 1)

        return (body, doc)

    def put_wrong_document_id(self, request_body, user='contributor'):
        response = self.app_put_json(
            self._prefix + '/9999999', request_body, status=403)

        headers = self.add_authorization_header(username=user)
        response = self.app_put_json(
            self._prefix + '/9999999', request_body, headers=headers,
            status=404)

        body = response.json
        self.assertEqual(body['status'], 'error')
        self.assertEqual(body['errors'][0]['name'], 'Not Found')

    def put_wrong_version(self, request_body, id, user='contributor'):
        response = self.app_put_json(
            self._prefix + '/' + str(id), request_body, status=403)

        headers = self.add_authorization_header(username=user)
        response = self.app_put_json(
            self._prefix + '/' + str(id), request_body, headers=headers,
            status=409)

        body = response.json
        self.assertEqual(body['status'], 'error')
        self.assertEqual(body['errors'][0]['name'], 'Conflict')

    def put_wrong_ids(self, request_body, id, user='contributor'):
        """The id given in the URL does not equal the document_id in the
        request body.
        """
        response = self.app_put_json(
            self._prefix + '/' + str(id + 1), request_body, status=403)

        headers = self.add_authorization_header(username=user)
        response = self.app_put_json(
            self._prefix + '/' + str(id + 1), request_body, headers=headers,
            status=400)
        body = response.json
        self.assertEqual(body['status'], 'error')
        self.assertEqual(body['errors'][0]['name'], 'Bad Request')

    def put_put_no_document(self, id, user='contributor'):
        request_body = {
            'message': '...'
        }
        response = self.app_put_json(
            self._prefix + '/' + str(id), request_body, status=403)

        headers = self.add_authorization_header(username=user)
        response = self.app_put_json(
            self._prefix + '/' + str(id), request_body, headers=headers,
            status=400)

        body = response.json
        self.assertEqual(body['status'], 'error')
        self.assertEqual(
            body['errors'][0]['description'], 'Required')

    def put_missing_field(
            self, request_body, document, field, user='contributor'):
        response = self.app_put_json(
            self._prefix + '/' + str(document.document_id), request_body,
            status=403)

        headers = self.add_authorization_header(username=user)
        response = self.app_put_json(
            self._prefix + '/' + str(document.document_id), request_body,
            headers=headers, status=400)

        body = response.json
        self.assertEqual(body.get('status'), 'error')
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertCorniceRequired(errors[0], field)

    def put_success_all(
            self, request_body, document, user='contributor', check_es=True,
            cache_version=2):
        """Test updating a document with changes to the figures and locales.
        """
        response = self.app_put_json(
            self._prefix + '/' + str(document.document_id), request_body,
            status=403)

        headers = self.add_authorization_header(username=user)
        self.app_put_json(
            self._prefix + '/' + str(document.document_id), request_body,
            headers=headers, status=200)

        response = self.app.get(
            self._prefix + '/' + str(document.document_id), headers=headers,
            status=200)
        self.assertEqual(response.content_type, 'application/json')

        body = response.json
        document_id = body.get('document_id')
        self.assertNotEqual(
            body.get('version'), document.version)
        self.assertEqual(body.get('document_id'), document_id)

        # check that the document was updated correctly
        self.session.expire_all()
        document = self.session.query(self._model).get(document_id)
        self.assertEqual(len(document.locales), 2)
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

        # version with lang 'en'
        version_en = self.get_latest_version('en', versions)

        self.assertEqual(version_en.lang, 'en')

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
        self.assertEqual(archive_locale.lang, 'en')

        # version with lang 'fr'
        version_fr = self.get_latest_version('fr', versions)

        self.assertEqual(version_fr.lang, 'fr')

        meta_data_fr = version_fr.history_metadata
        self.assertIs(meta_data_en, meta_data_fr)

        archive_document_fr = version_fr.document_archive
        self.assertIs(archive_document_en, archive_document_fr)

        archive_locale_fr = version_fr.document_locales_archive
        self.assertEqual(archive_locale_fr.document_id, document_id)
        self.assertEqual(
            archive_locale_fr.version, self.locale_fr.version)
        self.assertEqual(archive_locale_fr.lang, 'fr')

        if check_es:
            sync_es(self.session)
            # check updates to the search index
            search_doc = search_documents[self._doc_type].get(
                id=document.document_id,
                index=elasticsearch_config['index'])

            self.assertEqual(search_doc['doc_type'], document.type)
            self.assertEqual(search_doc['title_en'], archive_locale.title)
            self.assertEqual(search_doc['title_fr'], archive_locale_fr.title)

        self.check_cache_version(document_id, cache_version)

        return (body, document)

    def put_success_figures_only(
            self, request_body, document, user='contributor', check_es=True):
        """Test updating a document with changes to the figures only.
        """
        response = self.app_put_json(
            self._prefix + '/' + str(document.document_id), request_body,
            status=403)

        headers = self.add_authorization_header(username=user)
        self.app_put_json(
            self._prefix + '/' + str(document.document_id), request_body,
            headers=headers, status=200)

        response = self.app.get(
            self._prefix + '/' + str(document.document_id), headers=headers,
            status=200)
        self.assertEqual(response.content_type, 'application/json')

        body = response.json
        document_id = body.get('document_id')
        self.assertNotEqual(
            body.get('version'), document.version)
        self.assertEqual(body.get('document_id'), document_id)

        # check that the document was updated correctly
        self.session.expire_all()
        document = self.session.query(self._model).get(document_id)
        self.assertEqual(len(document.locales), 2)

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

        # version with lang 'en'
        version_en = self.get_latest_version('en', versions)

        self.assertEqual(version_en.lang, 'en')

        meta_data_en = version_en.history_metadata
        self.assertEqual(meta_data_en.comment, 'Changing figures')
        self.assertIsNotNone(meta_data_en.written_at)

        # version with lang 'fr'
        version_fr = self.get_latest_version('fr', versions)

        self.assertEqual(version_fr.lang, 'fr')

        meta_data_fr = version_fr.history_metadata
        self.assertIs(meta_data_en, meta_data_fr)

        archive_document_en = version_en.document_archive
        archive_document_fr = version_fr.document_archive
        self.assertIs(archive_document_en, archive_document_fr)

        # check updates to the search index
        sync_es(self.session)
        search_doc = search_documents[self._doc_type].get(
            id=document.document_id,
            index=elasticsearch_config['index'])

        self.assertEqual(search_doc['doc_type'], document.type)

        if isinstance(document, Route) and document.main_waypoint_id:
            locale_en = document.get_locale('en')
            title = locale_en.title_prefix + ' : ' + locale_en.title
            self.assertEqual(search_doc['title_en'], title)

            locale_fr = document.get_locale('fr')
            title = locale_fr.title_prefix + ' : ' + locale_fr.title
            self.assertEqual(search_doc['title_fr'], title)
        elif check_es:
            self.assertEqual(
                search_doc['title_en'], document.get_locale('en').title)
            self.assertEqual(
                search_doc['title_fr'], document.get_locale('fr').title)

        return (body, document)

    def put_success_lang_only(
            self, request_body, document, user='contributor', check_es=True):
        """Test updating a document with only changes to a locale.
        """
        response = self.app_put_json(
            self._prefix + '/' + str(document.document_id), request_body,
            status=403)

        headers = self.add_authorization_header(username=user)
        self.app_put_json(
            self._prefix + '/' + str(document.document_id), request_body,
            headers=headers, status=200)

        response = self.app.get(
            self._prefix + '/' + str(document.document_id), headers=headers,
            status=200)
        self.assertEqual(response.content_type, 'application/json')

        body = response.json
        document_id = body.get('document_id')
        # document version does not change!
        self.assertEqual(body.get('version'), document.version)
        self.assertEqual(body.get('document_id'), document_id)

        # check that the document was updated correctly
        self.session.expire_all()
        document = self.session.query(self._model).get(document_id)
        self.assertEqual(len(document.locales), 2)

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

        # version with lang 'en'
        version_en = self.get_latest_version('en', versions)

        self.assertEqual(version_en.lang, 'en')

        meta_data_en = version_en.history_metadata
        self.assertEqual(meta_data_en.comment, 'Changing lang')
        self.assertIsNotNone(meta_data_en.written_at)

        # version with lang 'fr'
        version_fr = self.get_latest_version('fr', versions)

        self.assertEqual(version_fr.lang, 'fr')

        meta_data_fr = version_fr.history_metadata
        self.assertIsNot(meta_data_en, meta_data_fr)

        archive_waypoint_en = version_en.document_archive
        archive_waypoint_fr = version_fr.document_archive
        self.assertIs(archive_waypoint_en, archive_waypoint_fr)

        # check updates to the search index
        if check_es:
            sync_es(self.session)
            search_doc = search_documents[self._doc_type].get(
                id=document.document_id,
                index=elasticsearch_config['index'])

            self.assertEqual(search_doc['doc_type'], document.type)
            self.assertEqual(
                search_doc['title_en'], document.get_locale('en').title)
            self.assertEqual(
                search_doc['title_fr'], document.get_locale('fr').title)

        return (body, document)

    def put_success_new_lang(
            self, request_body, document, user='contributor', check_es=True):
        """Test updating a document by adding a new locale.
        """
        response = self.app_put_json(
            self._prefix + '/' + str(document.document_id), request_body,
            status=403)

        headers = self.add_authorization_header(username=user)
        self.app_put_json(
            self._prefix + '/' + str(document.document_id), request_body,
            headers=headers, status=200)

        response = self.app.get(
            self._prefix + '/' + str(document.document_id), headers=headers,
            status=200)
        self.assertEqual(response.content_type, 'application/json')

        body = response.json
        document_id = body.get('document_id')
        # document version does not change!
        self.assertEqual(body.get('version'), document.version)
        self.assertEqual(body.get('document_id'), document_id)

        # check that the document was updated correctly
        self.session.expire_all()
        document = self.session.query(self._model).get(document_id)
        self.assertEqual(len(document.locales), 3)

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

        # version with lang 'en'
        version_en = self.get_latest_version('en', versions)
        self.assertEqual(version_en.lang, 'en')

        meta_data_en = version_en.history_metadata

        # version with lang 'fr'
        version_fr = self.get_latest_version('fr', versions)
        self.assertEqual(version_fr.lang, 'fr')

        meta_data_fr = version_fr.history_metadata
        self.assertIs(meta_data_en, meta_data_fr)

        archive_document_en = version_en.document_archive
        archive_document_fr = version_fr.document_archive
        self.assertIs(archive_document_en, archive_document_fr)

        # version with lang 'es'
        version_es = self.get_latest_version('es', versions)
        self.assertEqual(version_es.lang, 'es')

        meta_data_es = version_es.history_metadata
        self.assertIsNot(meta_data_en, meta_data_es)

        archive_document_es = version_es.document_archive
        self.assertIs(archive_document_es, archive_document_fr)

        # check updates to the search index
        if check_es:
            sync_es(self.session)
            search_doc = search_documents[self._doc_type].get(
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

    def _get_association_logs(self, document):
        url = '/associations-history?d={}'.format(
            document.document_id
        )

        resp = self.app.get(url, status=200)
        self.assertIsInstance(resp.json['count'], int)
        associations = resp.json["associations"]

        self.assertNotEqual(
            len(associations),
            0,
            "Need at least one association")

        for association in associations:
            self._assert_association_log_structure(
                association,
                document.document_id)

        return associations

    def _assert_association_log_structure(self, log, document_id):
        self.assertIsNotNone(log['written_at'])
        self.assertIsInstance(log['is_creation'], bool)

        user = log['user']
        self.assertIsInstance(user['user_id'], int)
        self.assertIsInstance(user['name'], str)
        self.assertIsInstance(user['forum_username'], str)
        self.assertIsInstance(user['robot'], bool)
        self.assertIsInstance(user['moderator'], bool)
        self.assertIsInstance(user['blocked'], bool)

        child = log['child_document']
        child_id = child['document_id']
        self.assertIsInstance(child_id, int)
        self.assertIsInstance(child['type'], str)
        self.assertIsInstance(child['locales'], list)

        parent = log['parent_document']
        parent_id = parent['document_id']
        self.assertIsInstance(parent_id, int)
        self.assertIsInstance(parent['type'], str)
        self.assertIsInstance(parent['locales'], list)

        self.assertTrue(child_id == document_id or parent_id == document_id)

        if parent["type"] == USERPROFILE_TYPE:
            self.assertIsInstance(parent["name"], str)

        if child["type"] == USERPROFILE_TYPE:
            self.assertIsInstance(child["name"], str)

    def _add_association(self, association, user_id):
        """ used for setup """
        self.session.add(association)
        self.session.add(association.get_log(user_id, is_creation=True))


def get_locale(locales, lang):
    return next(filter(lambda locale: locale['lang'] == lang, locales), None)
