import json
import urllib.error
import urllib.parse
import urllib.request

import pytest
from dateutil import parser as datetime_parser
from dogpile.cache.api import NO_VALUE

from c2corg_api.caching import cache_document_detail
from c2corg_api.models.cache_version import CacheVersion, get_cache_key
from c2corg_api.models.feed import DocumentChange
from c2corg_api.models.route import Route
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import USERPROFILE_TYPE, UserProfile
from c2corg_api.scripts.es.sync import sync_es
from c2corg_api.search import elasticsearch_config, search_documents
from c2corg_api.tests import BaseTestCase


class BaseTestRest(BaseTestCase):
    def assertErrorsContain(self, body, key, value=None):  # noqa
        for error in body['errors']:
            if error.get('name') == key:
                if value is not None:
                    assert error.get('description') == value
                return
        pytest.fail(str(body) + ' does not contain ' + key)

    def assertBodyEqual(self, body, key, expected):  # noqa
        assert body.get(key) == expected

    def add_authorization_header(self, username=None, token=None, headers=None):
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
        assert error.get('description') == key + ' is missing'
        assert error.get('name') == key

    def assertCorniceNotInEnum(self, error, key):  # noqa
        assert 'is not one of' in error.get('description')
        assert error.get('name') == key

    def assertCorniceRequired(self, error, key):  # noqa
        assert error.get('description') == 'Required'
        assert error.get('name') == key

    def assertError(self, errors, name, description):  # noqa
        for error in errors:
            if description == error.get('description') and name == error.get('name'):
                return
        pytest.fail('no error ({}, {}) in {}'.format(name, description, errors))

    def get_error(self, errors, name):  # noqa
        for error in errors:
            if name == error.get('name'):
                return error
        pytest.fail('no error for {0}'.format(name))

    def post_json_with_token(self, url, token, body={}, status=200):
        headers = self.add_authorization_header(token=token)
        r = self.app_post_json(url, body, headers=headers, status=status)
        return r.json

    def post_json_with_contributor(
        self, url, body={}, status=200, username='contributor', headers={}
    ):
        headers = self.add_authorization_header(username=username, headers=headers)
        r = self.app_post_json(url, body, headers=headers, status=status)
        return r.json

    def assertNotifiedEs(self):  # noqa
        queue = self.queue_config.queue(self.queue_config.connection)
        assert queue.get() is not None, 'no sync. notification sent for ES'

    def assertNotNotifiedEs(self):  # noqa
        queue = self.queue_config.queue(self.queue_config.connection)
        assert queue.get() is None, 'unexpected sync. notification sent for ES'

    def sync_es(self):
        self.assertNotifiedEs()
        sync_es(self.session)

    def get_latest_version(self, lang, versions):
        versions_in_lang = [v for v in versions if v.lang == lang]
        versions_in_lang.sort(key=lambda v: v.id, reverse=True)
        return versions_in_lang[0]

    def get_locale(self, lang, locales):
        return next(filter(lambda locale: locale['lang'] == lang, locales), None)

    def check_cache_version(self, document_id, version):
        cache_version = self.session.get(CacheVersion, document_id)
        assert cache_version is not None
        assert cache_version.version == version

    def get_feed_change(self, document_id, change_type=None):
        q = self.session.query(DocumentChange).filter(
            DocumentChange.document_id == document_id
        )

        if change_type:
            q = q.filter(DocumentChange.change_type == change_type)

        return q.first()


class BaseDocumentTestRest(BaseTestRest):
    def set_prefix_and_model(
        self, prefix, doc_type, model, model_archive, model_archive_locale
    ):
        self._prefix = prefix
        self._doc_type = doc_type
        self._model = model
        self._model_archive = model_archive
        self._model_archive_locale = model_archive_locale

    def get_collection(self, params=None, user=None):
        prefix = self._prefix
        limit = None
        if params:
            prefix += '?' + urllib.parse.urlencode(params)
            limit = params['limit']

        headers = {} if not user else self.add_authorization_header(username=user)

        response = self.app.get(prefix, headers=headers, status=200)
        assert response.content_type == 'application/json'

        body = response.json
        documents = body['documents']
        assert isinstance(documents, list)

        if params is None:
            doc = documents[0]
            available_langs = doc.get('available_langs')
            assert sorted(available_langs) == ['en', 'fr']
            assert 'protected' in doc
            assert 'type' in doc

        if limit is None:
            if self._model == UserProfile:
                nb_docs = (
                    self.session.query(UserProfile)
                    .join(User)
                    .filter(User.email_validated)
                    .filter(UserProfile.redirects_to.is_(None))
                    .count()
                )
            else:
                nb_docs = (
                    self.session.query(self._model)
                    .filter(getattr(self._model, 'redirects_to').is_(None))
                    .count()
                )
            assert len(documents) == nb_docs
        else:
            assert len(documents) <= limit

        return body

    def get_collection_search(self, params=None, user=None):
        prefix = self._prefix
        if params:
            prefix += '?' + urllib.parse.urlencode(params)

        headers = {} if not user else self.add_authorization_header(username=user)

        response = self.app.get(prefix, headers=headers, status=200)
        assert response.content_type == 'application/json'

        return response.json

    def get_collection_lang(self, user=None):
        headers = {} if not user else self.add_authorization_header(username=user)

        response = self.app.get(self._prefix + '?pl=es', headers=headers, status=200)
        assert response.content_type == 'application/json'

        body = response.json
        documents = body['documents']
        assert isinstance(documents, list)

        doc = documents[0]
        locales = doc.get('locales')
        assert len(locales) == 1
        locale = locales[0]
        assert 'fr' == locale['lang']
        assert 'protected' in doc
        assert 'type' in doc

        return body

    def assertResultsEqual(self, actual, expected, total):  # noqa
        actual_docs = actual['documents']
        actual_ids = [json['document_id'] for json in actual_docs]
        assert actual_ids == expected
        actual_total = actual['total']
        assert actual_total == total

    def get(self, reference, user=None, check_title=True, ignore_checks=False):
        headers = {} if not user else self.add_authorization_header(username=user)
        response = self.app.get(
            self._prefix + '/' + str(reference.document_id), headers=headers, status=200
        )
        assert response.content_type == 'application/json'

        body = response.json
        assert 'id' not in body
        assert body.get('document_id') == reference.document_id
        assert body.get('version') is not None
        assert 'type' in body
        assert body.get('associations') is not None

        locales = body.get('locales')
        if ignore_checks is False:
            assert len(locales) == 2
        locale_en = get_locale(locales, 'en')
        assert 'id' not in locale_en
        assert locale_en.get('version') is not None
        assert locale_en.get('lang') == self.locale_en.lang
        if check_title:
            assert locale_en.get('title') == self.locale_en.title

        available_langs = body.get('available_langs')
        if ignore_checks is False:
            assert sorted(available_langs) == sorted(['en', 'fr'])
        return body

    def get_caching(self, reference, user=None):
        headers = {} if not user else self.add_authorization_header(username=user)

        url = '{0}/{1}'.format(self._prefix, str(reference.document_id))
        cache_key = get_cache_key(
            reference.document_id, None, document_type=self._doc_type
        )

        cache_value = cache_document_detail.get(cache_key)

        assert cache_value == NO_VALUE

        # check that the response is cached
        self.app.get(url, headers=headers, status=200)

        cache_value = cache_document_detail.get(cache_key)
        assert cache_value != NO_VALUE

        # check that values are returned from the cache
        fake_cache_value = {'document': 'fake doc'}
        cache_document_detail.set(cache_key, fake_cache_value)

        response = self.app.get(url, headers=headers, status=200)
        body = response.json
        assert body == fake_cache_value

        # check that cache handles document types
        prefix = '/routes' if self._prefix != '/routes' else '/waypoint'
        url = '{0}/{1}'.format(prefix, str(reference.document_id))
        self.app.get(url, headers=headers, status=404)

    def get_version(self, reference, reference_version, user=None):
        headers = {} if not user else self.add_authorization_header(username=user)
        response = self.app.get(
            '{0}/{1}/en/{2}'.format(
                self._prefix, str(reference.document_id), str(reference_version.id)
            ),
            headers=headers,
            status=200,
        )
        assert response.content_type == 'application/json'

        body = response.json
        assert 'document' in body

        assert 'cooked' in body['document']
        assert 'lang' in body['document']['cooked']
        assert body['document']['cooked']['lang'] == 'en'

        assert 'version' in body
        assert 'previous_version_id' in body
        assert 'next_version_id' in body
        assert body['document']['document_id'] == reference.document_id
        assert body['version']['version_id'] == reference_version.id

        version = body['version']
        written_at = version['written_at']
        time = datetime_parser.parse(written_at)
        assert time.tzinfo is not None

        return body

    def get_info(self, reference, lang):
        response = self.app.get(
            '{0}/{1}/{2}/info'.format(self._prefix, str(reference.document_id), lang),
            status=200,
        )
        assert response.content_type == 'application/json'

        body = response.json
        assert 'document_id' in body
        assert 'locales' in body
        assert body['document_id'] == reference.document_id
        assert len(body['locales']) == 1
        locale = body['locales'][0]
        assert 'lang' in locale
        assert 'title_prefix' in locale
        assert 'title' in locale
        return body, locale

    def get_info_404(self):
        self.app.get(self._prefix + '/9999999/en/info', status=404)

    def _get_cooked(self, reference, lang, user=None):
        headers = {} if not user else self.add_authorization_header(username=user)

        response = self.app.get(
            self._prefix + '/' + str(reference.document_id) + '?cook=' + lang,
            headers=headers,
            status=200,
        )
        assert response.content_type == 'application/json'

        body = response.json
        assert 'cooked' in body
        assert 'locales' in body

        locales = body.get('locales')
        cooked = body.get('cooked')

        assert len(locales) == 1

        return body, locales[0], cooked

    def get_cooked(self, reference, user=None):
        body, locale, cooked = self._get_cooked(reference, 'en', user)

        assert locale.get('lang') == self.locale_en.lang
        assert locale.get('lang') == 'en'
        assert cooked.get('lang') == 'en'

        return body

    def get_cooked_with_defaulting(self, reference, user=None):
        body, locale, cooked = self._get_cooked(reference, 'it', user)

        assert locale.get('lang') == 'fr'
        assert cooked.get('lang') == 'fr'

        return body

    def get_lang(self, reference, user=None):
        headers = {} if not user else self.add_authorization_header(username=user)

        response = self.app.get(
            self._prefix + '/' + str(reference.document_id) + '?l=en',
            headers=headers,
            status=200,
        )
        assert response.content_type == 'application/json'

        body = response.json
        locales = body.get('locales')
        assert len(locales) == 1
        locale_en = locales[0]
        assert locale_en.get('lang') == self.locale_en.lang
        assert 'protected' in body
        assert 'topic_id' in locale_en
        return body

    def get_new_lang(self, reference, user=None):
        headers = {} if not user else self.add_authorization_header(username=user)

        response = self.app.get(
            self._prefix + '/' + str(reference.document_id) + '?l=it',
            headers=headers,
            status=200,
        )
        assert response.content_type == 'application/json'

        body = response.json
        locales = body.get('locales')
        assert len(locales) == 0

    def get_404(self, user=None):
        headers = {} if not user else self.add_authorization_header(username=user)

        self.app.get(self._prefix + '/9999999', headers=headers, status=404)
        self.app.get(self._prefix + '/9999999?l=es', headers=headers, status=404)

    def post_error(self, request_body, user='contributor'):
        response = self.app_post_json(
            self._prefix, request_body, expect_errors=True, status=403
        )

        headers = self.add_authorization_header(username=user)
        response = self.app_post_json(
            self._prefix, request_body, headers=headers, expect_errors=True, status=400
        )

        body = response.json
        assert body.get('status') == 'error'
        errors = body.get('errors')
        assert len(errors) > 0
        return body

    def post_missing_title(self, request_body, user='contributor', prefix=''):
        response = self.app_post_json(
            self._prefix, request_body, expect_errors=True, status=403
        )

        headers = self.add_authorization_header(username=user)
        response = self.app_post_json(
            self._prefix, request_body, headers=headers, expect_errors=True, status=400
        )

        body = response.json
        assert body.get('status') == 'error'
        errors = body.get('errors')
        self.assertCorniceRequired(errors[0], prefix + 'locales.0.title')
        return body

    def post_missing_geometry(self, request_body):
        response = self.app_post_json(
            self._prefix, request_body, expect_errors=True, status=403
        )

        headers = self.add_authorization_header(username='contributor')
        response = self.app_post_json(
            self._prefix, request_body, headers=headers, expect_errors=True, status=400
        )

        body = response.json
        assert body.get('status') == 'error'
        errors = body.get('errors')
        assert len(errors) == 1
        self.assertCorniceRequired(errors[0], 'geometry')
        return body

    def post_missing_geom(self, request_body):
        response = self.app_post_json(
            self._prefix, request_body, expect_errors=True, status=403
        )

        headers = self.add_authorization_header(username='contributor')
        response = self.app_post_json(
            self._prefix, request_body, headers=headers, expect_errors=True, status=400
        )

        body = response.json
        assert body.get('status') == 'error'
        errors = body.get('errors')
        assert len(errors) == 1
        self.assertCorniceRequired(errors[0], 'geometry.geom')
        return body

    def post_wrong_geom_type(self, request_body):
        response = self.app_post_json(
            self._prefix, request_body, expect_errors=True, status=403
        )

        headers = self.add_authorization_header(username='contributor')
        response = self.app_post_json(
            self._prefix, request_body, headers=headers, expect_errors=True, status=400
        )

        body = response.json
        assert body.get('status') == 'error'
        errors = body.get('errors')
        return errors

    def post_missing_locales(self, request_body):
        response = self.app_post_json(
            self._prefix, request_body, expect_errors=True, status=403
        )

        headers = self.add_authorization_header(username='contributor')
        response = self.app_post_json(
            self._prefix, request_body, headers=headers, expect_errors=True, status=400
        )

        body = response.json
        assert body.get('status') == 'error'
        errors = body.get('errors')
        assert len(errors) == 1
        assert errors[0].get('description') == 'Required'
        assert errors[0].get('name') == 'locales'
        return body

    def post_same_locale_twice(self, request_body):
        response = self.app_post_json(
            self._prefix, request_body, expect_errors=True, status=403
        )

        headers = self.add_authorization_header(username='contributor')
        response = self.app_post_json(
            self._prefix, request_body, headers=headers, expect_errors=True, status=400
        )

        body = response.json
        assert body.get('status') == 'error'
        errors = body.get('errors')
        assert len(errors) == 1
        assert 'lang "en" is given twice' in errors[0].get('description')
        return body

    def post_missing_field(self, request_body, field):
        response = self.app_post_json(
            self._prefix, request_body, expect_errors=True, status=403
        )

        headers = self.add_authorization_header(username='contributor')
        response = self.app_post_json(
            self._prefix, request_body, headers=headers, expect_errors=True, status=400
        )

        body = response.json
        assert body.get('status') == 'error'
        errors = body.get('errors')
        assert len(errors) == 1
        assert errors[0].get('description') == 'Required'
        assert errors[0].get('name') == field
        return body

    def post_non_whitelisted_attribute(self, request_body, user='contributor'):
        """`protected` is a non-whitelisted attribute, which is ignored when
        given in a request.
        """
        response = self.app_post_json(self._prefix, request_body, status=403)

        headers = self.add_authorization_header(username=user)
        response = self.app_post_json(
            self._prefix, request_body, headers=headers, status=200
        )

        body = response.json
        document_id = body.get('document_id')
        document = self.session.get(self._model, document_id)
        # the value for `protected` was ignored
        assert not document.protected
        return (body, document)

    def post_missing_content_type(self, request_body):
        response = self.app.post(
            self._prefix, params=json.dumps(request_body), status=415
        )

        body = response.json
        assert body.get('status') == 'error'
        errors = body.get('errors')
        assert len(errors) == 1
        assert errors[0].get('location') == 'header'
        assert errors[0].get('name') == 'Content-Type'
        return body

    def post_success(
        self,
        request_body,
        user='contributor',
        validate_with_auth=False,
        skip_validation=False,
    ):
        response = self.app_post_json(self._prefix, request_body, status=403)

        headers = self.add_authorization_header(username=user)
        response = self.app_post_json(
            self._prefix, request_body, headers=headers, status=200
        )

        body = response.json
        if skip_validation:
            document_id = body.get('document_id')
            response = self.app.get(self._prefix + '/' + str(document_id), status=200)
            doc = self.session.get(self._model, document_id)
            return response.json, doc
        else:
            return self._validate_document(body, headers, validate_with_auth)

    def _validate_document(self, body, headers=None, validate_with_auth=False):
        document_id = body.get('document_id')
        assert document_id is not None

        if validate_with_auth:
            response = self.app.get(
                self._prefix + '/' + str(document_id), headers=headers, status=200
            )
        else:
            response = self.app.get(self._prefix + '/' + str(document_id), status=200)
        assert response.content_type == 'application/json'

        body = response.json
        assert body.get('version') is not None
        assert body.get('protected') == False

        # check that the version was created correctly
        doc = self.session.get(self._model, document_id)
        assert 1 == doc.version
        versions = doc.versions
        assert len(versions) == 1
        version = versions[0]

        lang = body.get('locales')[0].get('lang')
        assert version.lang == lang

        meta_data = version.history_metadata
        assert meta_data.comment == 'creation'
        assert meta_data.written_at is not None

        archive_doc = version.document_archive
        assert archive_doc.document_id == document_id
        assert archive_doc.version == doc.version

        archive_locale = version.document_locales_archive
        waypoint_locale_en = doc.locales[0]
        assert 1 == waypoint_locale_en.version
        assert archive_locale.version == waypoint_locale_en.version
        assert archive_locale.document_id == document_id
        assert archive_locale.lang == lang

        # check updates to the search index
        self.sync_es()
        search_doc = search_documents[self._doc_type].get(
            id=doc.document_id, index=elasticsearch_config['index']
        )

        assert search_doc['doc_type'] is not None
        assert search_doc['doc_type'] == doc.type

        if isinstance(doc, Route):
            title = waypoint_locale_en.title_prefix + ' : ' + waypoint_locale_en.title
            assert search_doc['title_en'] == title
        else:
            assert search_doc['title_en'] == waypoint_locale_en.title

        cache_version = self.session.get(CacheVersion, document_id)
        assert cache_version is not None
        assert cache_version.version == 1

        return (body, doc)

    def put_wrong_document_id(self, request_body, user='contributor'):
        response = self.app_put_json(
            self._prefix + '/9999999', request_body, status=403
        )

        headers = self.add_authorization_header(username=user)
        response = self.app_put_json(
            self._prefix + '/9999999', request_body, headers=headers, status=404
        )

        body = response.json
        assert body['status'] == 'error'
        assert body['errors'][0]['name'] == 'Not Found'

    def put_wrong_version(self, request_body, id, user='contributor'):
        response = self.app_put_json(
            self._prefix + '/' + str(id), request_body, status=403
        )

        headers = self.add_authorization_header(username=user)
        response = self.app_put_json(
            self._prefix + '/' + str(id), request_body, headers=headers, status=409
        )

        body = response.json
        assert body['status'] == 'error'
        assert body['errors'][0]['name'] == 'Conflict'

    def put_wrong_ids(self, request_body, id, user='contributor'):
        """The id given in the URL does not equal the document_id in the
        request body.
        """
        response = self.app_put_json(
            self._prefix + '/' + str(id + 1), request_body, status=403
        )

        headers = self.add_authorization_header(username=user)
        response = self.app_put_json(
            self._prefix + '/' + str(id + 1), request_body, headers=headers, status=400
        )
        body = response.json
        assert body['status'] == 'error'
        assert body['errors'][0]['name'] == 'Bad Request'

    def put_put_no_document(self, id, user='contributor'):
        request_body = {'message': '...'}
        self.app_put_json(self._prefix + '/' + str(id), request_body, status=403)

        headers = self.add_authorization_header(username=user)
        response = self.app_put_json(
            self._prefix + '/' + str(id), request_body, headers=headers, status=400
        )

        body = response.json
        assert body['status'] == 'error'
        assert body['errors'][0]['description'] == 'Required'

    def put_missing_field(self, request_body, document, field, user='contributor'):
        response = self.app_put_json(
            self._prefix + '/' + str(document.document_id), request_body, status=403
        )

        headers = self.add_authorization_header(username=user)
        response = self.app_put_json(
            self._prefix + '/' + str(document.document_id),
            request_body,
            headers=headers,
            status=400,
        )

        body = response.json
        assert body.get('status') == 'error'
        errors = body.get('errors')
        assert len(errors) == 1
        self.assertCorniceRequired(errors[0], field)

    def put_success_all(
        self, request_body, document, user='contributor', check_es=True, cache_version=2
    ):
        """Test updating a document with changes to the figures and locales."""
        response = self.app_put_json(
            self._prefix + '/' + str(document.document_id), request_body, status=403
        )

        headers = self.add_authorization_header(username=user)
        self.app_put_json(
            self._prefix + '/' + str(document.document_id),
            request_body,
            headers=headers,
            status=200,
        )

        response = self.app.get(
            self._prefix + '/' + str(document.document_id), headers=headers, status=200
        )
        assert response.content_type == 'application/json'

        body = response.json
        document_id = body.get('document_id')
        assert body.get('version') != document.version
        assert body.get('document_id') == document_id

        # check that the document was updated correctly
        self.session.expire_all()
        document = self.session.get(self._model, document_id)
        assert len(document.locales) == 2
        locale_en = document.get_locale('en')

        # check that a new archive_document was created
        archive_count = (
            self.session.query(self._model_archive)
            .filter(getattr(self._model_archive, 'document_id') == document_id)
            .count()
        )
        assert archive_count == 2

        # check that only one new archive_document_locale was created (only
        # for 'en' not 'fr')
        archive_locale_count = (
            self.session.query(self._model_archive_locale)
            .filter(document_id == getattr(self._model_archive_locale, 'document_id'))
            .count()
        )
        assert archive_locale_count == 3

        # check that new versions were created
        versions = document.versions
        assert len(versions) == 4

        # version with lang 'en'
        version_en = self.get_latest_version('en', versions)

        assert version_en.lang == 'en'

        meta_data_en = version_en.history_metadata
        assert meta_data_en.comment == 'Update'
        assert meta_data_en.written_at is not None

        archive_document_en = version_en.document_archive
        assert archive_document_en.document_id == document_id
        assert archive_document_en.version == document.version

        archive_locale = version_en.document_locales_archive
        assert archive_locale.document_id == document_id
        assert archive_locale.version == locale_en.version
        assert archive_locale.lang == 'en'

        # version with lang 'fr'
        version_fr = self.get_latest_version('fr', versions)

        assert version_fr.lang == 'fr'

        meta_data_fr = version_fr.history_metadata
        assert meta_data_en is meta_data_fr

        archive_document_fr = version_fr.document_archive
        assert archive_document_en is archive_document_fr

        archive_locale_fr = version_fr.document_locales_archive
        assert archive_locale_fr.document_id == document_id
        assert archive_locale_fr.version == self.locale_fr.version
        assert archive_locale_fr.lang == 'fr'

        if check_es:
            sync_es(self.session)
            # check updates to the search index
            search_doc = search_documents[self._doc_type].get(
                id=document.document_id, index=elasticsearch_config['index']
            )

            assert search_doc['doc_type'] == document.type
            assert search_doc['title_en'] == archive_locale.title
            assert search_doc['title_fr'] == archive_locale_fr.title

        self.check_cache_version(document_id, cache_version)

        return (body, document)

    def put_success_figures_only(
        self, request_body, document, user='contributor', check_es=True
    ):
        """Test updating a document with changes to the figures only."""
        response = self.app_put_json(
            self._prefix + '/' + str(document.document_id), request_body, status=403
        )

        headers = self.add_authorization_header(username=user)
        self.app_put_json(
            self._prefix + '/' + str(document.document_id),
            request_body,
            headers=headers,
            status=200,
        )

        response = self.app.get(
            self._prefix + '/' + str(document.document_id), headers=headers, status=200
        )
        assert response.content_type == 'application/json'

        body = response.json
        document_id = body.get('document_id')
        assert body.get('version') != document.version
        assert body.get('document_id') == document_id

        # check that the document was updated correctly
        self.session.expire_all()
        document = self.session.get(self._model, document_id)
        assert len(document.locales) == 2

        # check that a new archive_document was created
        archive_count = (
            self.session.query(self._model_archive)
            .filter(getattr(self._model_archive, 'document_id') == document_id)
            .count()
        )
        assert archive_count == 2

        # check that no new archive_document_locale was created
        archive_locale_count = (
            self.session.query(self._model_archive_locale)
            .filter(document_id == getattr(self._model_archive_locale, 'document_id'))
            .count()
        )
        assert archive_locale_count == 2

        # check that new versions were created
        versions = document.versions
        assert len(versions) == 4

        # version with lang 'en'
        version_en = self.get_latest_version('en', versions)

        assert version_en.lang == 'en'

        meta_data_en = version_en.history_metadata
        assert meta_data_en.comment == 'Changing figures'
        assert meta_data_en.written_at is not None

        # version with lang 'fr'
        version_fr = self.get_latest_version('fr', versions)

        assert version_fr.lang == 'fr'

        meta_data_fr = version_fr.history_metadata
        assert meta_data_en is meta_data_fr

        archive_document_en = version_en.document_archive
        archive_document_fr = version_fr.document_archive
        assert archive_document_en is archive_document_fr

        # check updates to the search index
        sync_es(self.session)
        search_doc = search_documents[self._doc_type].get(
            id=document.document_id, index=elasticsearch_config['index']
        )

        assert search_doc['doc_type'] == document.type

        if isinstance(document, Route) and document.main_waypoint_id:
            locale_en = document.get_locale('en')
            title = locale_en.title_prefix + ' : ' + locale_en.title
            assert search_doc['title_en'] == title

            locale_fr = document.get_locale('fr')
            title = locale_fr.title_prefix + ' : ' + locale_fr.title
            assert search_doc['title_fr'] == title
        elif check_es:
            assert search_doc['title_en'] == document.get_locale('en').title
            assert search_doc['title_fr'] == document.get_locale('fr').title

        return (body, document)

    def put_success_lang_only(
        self, request_body, document, user='contributor', check_es=True
    ):
        """Test updating a document with only changes to a locale."""
        response = self.app_put_json(
            self._prefix + '/' + str(document.document_id), request_body, status=403
        )

        headers = self.add_authorization_header(username=user)
        self.app_put_json(
            self._prefix + '/' + str(document.document_id),
            request_body,
            headers=headers,
            status=200,
        )

        response = self.app.get(
            self._prefix + '/' + str(document.document_id), headers=headers, status=200
        )
        assert response.content_type == 'application/json'

        body = response.json
        document_id = body.get('document_id')
        # document version does not change!
        assert body.get('version') == document.version
        assert body.get('document_id') == document_id

        # check that the document was updated correctly
        self.session.expire_all()
        document = self.session.get(self._model, document_id)
        assert len(document.locales) == 2

        # check that no new archive_document was created
        archive_count = (
            self.session.query(self._model_archive)
            .filter(getattr(self._model_archive, 'document_id') == document_id)
            .count()
        )

        assert archive_count == 1

        # check that one new archive_document_locale was created
        archive_locale_count = (
            self.session.query(self._model_archive_locale)
            .filter(document_id == getattr(self._model_archive_locale, 'document_id'))
            .count()
        )
        assert archive_locale_count == 3

        # check that one new version was created
        versions = document.versions
        assert len(versions) == 3

        # version with lang 'en'
        version_en = self.get_latest_version('en', versions)

        assert version_en.lang == 'en'

        meta_data_en = version_en.history_metadata
        assert meta_data_en.comment == 'Changing lang'
        assert meta_data_en.written_at is not None

        # version with lang 'fr'
        version_fr = self.get_latest_version('fr', versions)

        assert version_fr.lang == 'fr'

        meta_data_fr = version_fr.history_metadata
        assert meta_data_en is not meta_data_fr

        archive_waypoint_en = version_en.document_archive
        archive_waypoint_fr = version_fr.document_archive
        assert archive_waypoint_en is archive_waypoint_fr

        # check updates to the search index
        if check_es:
            sync_es(self.session)
            search_doc = search_documents[self._doc_type].get(
                id=document.document_id, index=elasticsearch_config['index']
            )

            assert search_doc['doc_type'] == document.type
            assert search_doc['title_en'] == document.get_locale('en').title
            assert search_doc['title_fr'] == document.get_locale('fr').title

        return (body, document)

    def put_success_new_lang(
        self, request_body, document, user='contributor', check_es=True
    ):
        """Test updating a document by adding a new locale."""
        response = self.app_put_json(
            self._prefix + '/' + str(document.document_id), request_body, status=403
        )

        headers = self.add_authorization_header(username=user)
        self.app_put_json(
            self._prefix + '/' + str(document.document_id),
            request_body,
            headers=headers,
            status=200,
        )

        response = self.app.get(
            self._prefix + '/' + str(document.document_id), headers=headers, status=200
        )
        assert response.content_type == 'application/json'

        body = response.json
        document_id = body.get('document_id')
        # document version does not change!
        assert body.get('version') == document.version
        assert body.get('document_id') == document_id

        # check that the document was updated correctly
        self.session.expire_all()
        document = self.session.get(self._model, document_id)
        assert len(document.locales) == 3

        # check that no new archive_document was created
        archive_count = (
            self.session.query(self._model_archive)
            .filter(getattr(self._model_archive, 'document_id') == document_id)
            .count()
        )

        assert archive_count == 1

        # check that one new archive_document_locale was created
        archive_locale_count = (
            self.session.query(self._model_archive_locale)
            .filter(document_id == getattr(self._model_archive_locale, 'document_id'))
            .count()
        )
        assert archive_locale_count == 3

        # check that one new version was created
        versions = document.versions
        assert len(versions) == 3

        # version with lang 'en'
        version_en = self.get_latest_version('en', versions)
        assert version_en.lang == 'en'

        meta_data_en = version_en.history_metadata

        # version with lang 'fr'
        version_fr = self.get_latest_version('fr', versions)
        assert version_fr.lang == 'fr'

        meta_data_fr = version_fr.history_metadata
        assert meta_data_en is meta_data_fr

        archive_document_en = version_en.document_archive
        archive_document_fr = version_fr.document_archive
        assert archive_document_en is archive_document_fr

        # version with lang 'es'
        version_es = self.get_latest_version('es', versions)
        assert version_es.lang == 'es'

        meta_data_es = version_es.history_metadata
        assert meta_data_en is not meta_data_es

        archive_document_es = version_es.document_archive
        assert archive_document_es is archive_document_fr

        # check updates to the search index
        if check_es:
            sync_es(self.session)
            search_doc = search_documents[self._doc_type].get(
                id=document.document_id, index=elasticsearch_config['index']
            )

            assert search_doc['doc_type'] == document.type
            assert search_doc['title_en'] == document.get_locale('en').title
            assert search_doc['title_fr'] == document.get_locale('fr').title
            assert search_doc['title_es'] == document.get_locale('es').title

        return (body, document)

    def _get_association_logs(self, document):
        url = '/associations-history?d={}'.format(document.document_id)

        resp = self.app.get(url, status=200)
        assert isinstance(resp.json['count'], int)
        associations = resp.json['associations']

        assert len(associations) != 0, 'Need at least one association'

        for association in associations:
            self._assert_association_log_structure(association, document.document_id)

        return associations

    def _assert_association_log_structure(self, log, document_id):
        assert log['written_at'] is not None
        assert isinstance(log['is_creation'], bool)

        user = log['user']
        assert isinstance(user['user_id'], int)
        assert isinstance(user['name'], str)
        assert isinstance(user['forum_username'], str)
        assert isinstance(user['robot'], bool)
        assert isinstance(user['moderator'], bool)
        assert isinstance(user['blocked'], bool)

        child = log['child_document']
        child_id = child['document_id']
        assert isinstance(child_id, int)
        assert isinstance(child['type'], str)
        assert isinstance(child['locales'], list)

        parent = log['parent_document']
        parent_id = parent['document_id']
        assert isinstance(parent_id, int)
        assert isinstance(parent['type'], str)
        assert isinstance(parent['locales'], list)

        assert child_id == document_id or parent_id == document_id

        if parent['type'] == USERPROFILE_TYPE:
            assert isinstance(parent['name'], str)

        if child['type'] == USERPROFILE_TYPE:
            assert isinstance(child['name'], str)

    def _add_association(self, association, user_id):
        """used for setup"""
        self.session.add(association)
        self.session.add(association.get_log(user_id, is_creation=True))


def get_locale(locales, lang):
    return next(filter(lambda locale: locale['lang'] == lang, locales), None)
