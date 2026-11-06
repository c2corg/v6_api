import json

import pytest

from c2corg_api.models.cache_version import CacheVersion
from c2corg_api.models.feed import DocumentChange
from c2corg_api.models.route import Route
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.scripts.es.sync import sync_es
from c2corg_api.search import elasticsearch_config, search_documents
from c2corg_api.tests import BaseTestCase, errors_of


class BaseTestRest(BaseTestCase):
    def assertErrorsContain(self, body, key, value=None):  # noqa
        for error in errors_of(body):
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
        # a missing field: FastAPI's text in a 422, the API's in its envelope
        assert error.get('description') in ('Field required', 'Required')
        assert error.get('name') == key

    def assertError(self, errors, name, description):  # noqa
        for error in errors:
            if description == error.get('description') and name == error.get('name'):
                return
        pytest.fail(f'no error ({name}, {description}) in {errors}')

    def get_error(self, errors, name):
        for error in errors:
            if name == error.get('name'):
                return error
        pytest.fail(f'no error for {name}')

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
    def set_doc_type(self, doc_type):
        # the post/put scenarios below still read these attributes
        self._prefix = doc_type.prefix
        self._doc_type = doc_type.type
        self._model = doc_type.model
        self._model_archive = doc_type.model_archive
        self._model_archive_locale = doc_type.model_archive_locale

    def post_error(self, request_body, user='contributor', status=400):
        response = self.app_post_json(
            self._prefix, request_body, expect_errors=True, status=403
        )

        headers = self.add_authorization_header(username=user)
        response = self.app_post_json(
            self._prefix,
            request_body,
            headers=headers,
            expect_errors=True,
            status=status,
        )

        body = response.json
        assert len(errors_of(body)) > 0
        return body

    def post_missing_title(self, request_body, user='contributor', prefix=''):
        response = self.app_post_json(
            self._prefix, request_body, expect_errors=True, status=403
        )

        headers = self.add_authorization_header(username=user)
        response = self.app_post_json(
            self._prefix, request_body, headers=headers, expect_errors=True, status=422
        )

        body = response.json
        errors = errors_of(body)
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

    def post_wrong_geom_type(self, request_body, status=400):
        response = self.app_post_json(
            self._prefix, request_body, expect_errors=True, status=403
        )

        headers = self.add_authorization_header(username='contributor')
        response = self.app_post_json(
            self._prefix,
            request_body,
            headers=headers,
            expect_errors=True,
            status=status,
        )

        return errors_of(response.json)

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
        assert errors[0].get('description') == 'lang "en" is given twice'
        assert errors[0].get('name') == 'locales'
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
        assert body.get('protected') is False

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
        response = self.app_put_json(
            self._prefix + '/' + str(id), request_body, status=403
        )

        headers = self.add_authorization_header(username=user)
        response = self.app_put_json(
            self._prefix + '/' + str(id), request_body, headers=headers, status=422
        )

        assert errors_of(response.json)[0]['description'] == 'Field required'

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
            .filter(self._model_archive.document_id == document_id)
            .count()
        )
        assert archive_count == 2

        # check that only one new archive_document_locale was created (only
        # for 'en' not 'fr')
        archive_locale_count = (
            self.session.query(self._model_archive_locale)
            .filter(document_id == self._model_archive_locale.document_id)
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
            .filter(self._model_archive.document_id == document_id)
            .count()
        )
        assert archive_count == 2

        # check that no new archive_document_locale was created
        archive_locale_count = (
            self.session.query(self._model_archive_locale)
            .filter(document_id == self._model_archive_locale.document_id)
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
        expected_version = 2 if document.type == 'r' else document.version
        assert body.get('version') == expected_version
        assert body.get('document_id') == document_id

        # check that the document was updated correctly
        self.session.expire_all()
        document = self.session.get(self._model, document_id)
        assert len(document.locales) == 2

        # check that no new archive_document was created
        archive_count = (
            self.session.query(self._model_archive)
            .filter(self._model_archive.document_id == document_id)
            .count()
        )

        expected_count = 2 if document.type == 'r' else 1
        assert archive_count == expected_count

        # check that one new archive_document_locale was created
        archive_locale_count = (
            self.session.query(self._model_archive_locale)
            .filter(document_id == self._model_archive_locale.document_id)
            .count()
        )
        assert archive_locale_count == 3

        # check that one new version was created
        versions = document.versions
        expected_count = 4 if document.type == 'r' else 3
        assert len(versions) == expected_count

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
        if document.type == 'r':
            assert meta_data_en == meta_data_fr
        else:
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
        expected_version = 2 if document.type == 'r' else document.version
        assert body.get('version') == expected_version
        assert body.get('document_id') == document_id

        # check that the document was updated correctly
        self.session.expire_all()
        document = self.session.get(self._model, document_id)
        assert len(document.locales) == 3

        # check that no new archive_document was created
        archive_count = (
            self.session.query(self._model_archive)
            .filter(self._model_archive.document_id == document_id)
            .count()
        )

        expected_count = 2 if document.type == 'r' else 1
        assert archive_count == expected_count

        # check that one new archive_document_locale was created
        archive_locale_count = (
            self.session.query(self._model_archive_locale)
            .filter(document_id == self._model_archive_locale.document_id)
            .count()
        )
        assert archive_locale_count == 3

        # check that one new version was created
        versions = document.versions
        expected_count = 5 if document.type == 'r' else 3
        assert len(versions) == expected_count

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
        if document.type == 'r':
            assert meta_data_en == meta_data_es
        else:
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
        url = f'/associations-history?d={document.document_id}'

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
