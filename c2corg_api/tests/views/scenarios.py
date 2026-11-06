"""Shared test scenarios of the document services, as plain functions."""

# Each scenario calls the API with the given test client and checks the
# answer. It takes the `DocType` of the documents under test: the URL prefix,
# the document type and the models used to check what was written.

import json
import urllib.parse
from collections import Counter
from dataclasses import dataclass

from dateutil import parser as datetime_parser
from dogpile.cache.api import NO_VALUE

from c2corg_api.caching import cache_document_detail
from c2corg_api.models.cache_version import CacheVersion, get_cache_key
from c2corg_api.models.route import Route
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import UserProfile
from c2corg_api.scripts.es.sync import sync_es
from c2corg_api.search import elasticsearch_config, search_documents
from c2corg_api.tests import (
    assert_required,
    errors_of,
    global_tokens,
    send_json,
)


@dataclass(frozen=True)
class DocType:
    """The documents a test is about: URL prefix, type letter and models."""

    prefix: str
    type: str
    model: type
    model_archive: type | None = None
    model_archive_locale: type | None = None


def auth_headers(username=None, token=None, headers=None):
    """Return the headers with the token of the given user (or token)."""
    if not headers:
        headers = {}
    if not token:
        token = global_tokens[username]
    headers['Authorization'] = 'JWT token="' + token + '"'
    return headers


def _user_headers(user):
    return {} if not user else auth_headers(username=user)


def get_locale(locales, lang):
    """Return the locale of the given language in a JSON list of locales."""
    return next(filter(lambda locale: locale['lang'] == lang, locales), None)


def assert_results_equal(actual, expected, total):
    """Check the document ids and the total of a listing."""
    actual_ids = [json['document_id'] for json in actual['documents']]
    assert actual_ids == expected
    assert actual['total'] == total


def get_collection(client, session, doc_type, params=None, user=None):
    """Get a listing and check its documents (all of them without a limit)."""
    url = doc_type.prefix
    limit = None
    if params:
        url += '?' + urllib.parse.urlencode(params)
        limit = params['limit']

    response = client.get(url, headers=_user_headers(user), status=200)
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
        assert 'license' in doc

    if limit is None:
        model = doc_type.model
        if model == UserProfile:
            nb_docs = (
                session.query(UserProfile)
                .join(User)
                .filter(User.email_validated)
                .filter(UserProfile.redirects_to.is_(None))
                .count()
            )
        else:
            nb_docs = session.query(model).filter(model.redirects_to.is_(None)).count()
        assert len(documents) == nb_docs
    else:
        assert len(documents) <= limit

    return body


def get_collection_search(client, doc_type, params=None, user=None):
    """Get a listing with search parameters."""
    url = doc_type.prefix
    if params:
        url += '?' + urllib.parse.urlencode(params)

    response = client.get(url, headers=_user_headers(user), status=200)
    assert response.content_type == 'application/json'

    return response.json


def get_collection_lang(client, doc_type, user=None):
    """Get a listing in a language without documents: the best one is used."""
    response = client.get(
        doc_type.prefix + '?pl=es', headers=_user_headers(user), status=200
    )
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


def get(client, doc_type, reference, user=None, title=None, ignore_checks=False):
    """Get a document in 'en' and 'fr'; check the 'en' title if given."""
    response = client.get(
        doc_type.prefix + '/' + str(reference.document_id),
        headers=_user_headers(user),
        status=200,
    )
    assert response.content_type == 'application/json'

    body = response.json
    assert 'id' not in body
    assert body.get('document_id') == reference.document_id
    assert body.get('version') is not None
    assert 'type' in body
    assert 'license' in body
    assert body.get('associations') is not None

    locales = body.get('locales')
    if ignore_checks is False:
        assert len(locales) == 2
    locale_en = get_locale(locales, 'en')
    assert 'id' not in locale_en
    assert locale_en.get('version') is not None
    assert locale_en.get('lang') == 'en'
    if title is not None:
        assert locale_en.get('title') == title

    available_langs = body.get('available_langs')
    if ignore_checks is False:
        assert Counter(available_langs) == Counter(['en', 'fr'])
    return body


def get_caching(client, doc_type, reference, user=None):
    """Check that the answer for a document is cached, by document type."""
    headers = _user_headers(user)

    url = f'{doc_type.prefix}/{reference.document_id!s}'
    cache_key = get_cache_key(reference.document_id, None, document_type=doc_type.type)

    cache_value = cache_document_detail.get(cache_key)

    assert cache_value == NO_VALUE

    # check that the response is cached
    client.get(url, headers=headers, status=200)

    cache_value = cache_document_detail.get(cache_key)
    assert cache_value != NO_VALUE

    # check that values are returned from the cache
    fake_cache_value = {'document': 'fake doc'}
    cache_document_detail.set(cache_key, fake_cache_value)

    response = client.get(url, headers=headers, status=200)
    body = response.json
    assert body == fake_cache_value

    # check that cache handles document types
    prefix = '/routes' if doc_type.prefix != '/routes' else '/waypoint'
    url = f'{prefix}/{reference.document_id!s}'
    client.get(url, headers=headers, status=404)


def get_version(client, doc_type, reference, reference_version, user=None):
    """Get a version of a document in 'en'."""
    response = client.get(
        f'{doc_type.prefix}/{reference.document_id!s}/en/{reference_version.id!s}',
        headers=_user_headers(user),
        status=200,
    )
    assert response.content_type == 'application/json'

    body = response.json
    assert 'document' in body

    assert 'cooked' in body['document']
    assert 'lang' in body['document']['cooked']
    assert body['document']['cooked']['lang'] == 'en'
    assert 'license' in body['document']

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


def get_info(client, doc_type, reference, lang):
    """Get the info of a document; return the answer and its locale."""
    response = client.get(
        f'{doc_type.prefix}/{reference.document_id!s}/{lang}/info',
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


def get_info_404(client, doc_type):
    """Check the info of a missing document."""
    client.get(doc_type.prefix + '/9999999/en/info', status=404)


def _get_cooked(client, doc_type, reference, lang, user=None):
    response = client.get(
        doc_type.prefix + '/' + str(reference.document_id) + '?cook=' + lang,
        headers=_user_headers(user),
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


def get_cooked(client, doc_type, reference, user=None):
    """Get a document with its 'en' locale cooked."""
    body, locale, cooked = _get_cooked(client, doc_type, reference, 'en', user)

    assert locale.get('lang') == 'en'
    assert cooked.get('lang') == 'en'

    return body


def get_cooked_with_defaulting(client, doc_type, reference, user=None):
    """Get a document cooked in a missing language: 'fr' is used."""
    body, locale, cooked = _get_cooked(client, doc_type, reference, 'it', user)

    assert locale.get('lang') == 'fr'
    assert cooked.get('lang') == 'fr'

    return body


def get_lang(client, doc_type, reference, user=None):
    """Get a document in 'en' only."""
    response = client.get(
        doc_type.prefix + '/' + str(reference.document_id) + '?l=en',
        headers=_user_headers(user),
        status=200,
    )
    assert response.content_type == 'application/json'

    body = response.json
    locales = body.get('locales')
    assert len(locales) == 1
    locale_en = locales[0]
    assert locale_en.get('lang') == 'en'
    assert 'protected' in body
    assert 'topic_id' in locale_en
    return body


def get_new_lang(client, doc_type, reference, user=None):
    """Get a document in a language it does not have: no locale."""
    response = client.get(
        doc_type.prefix + '/' + str(reference.document_id) + '?l=it',
        headers=_user_headers(user),
        status=200,
    )
    assert response.content_type == 'application/json'

    body = response.json
    locales = body.get('locales')
    assert len(locales) == 0


def get_404(client, doc_type, user=None):
    """Get a missing document, with and without a language."""
    headers = _user_headers(user)

    client.get(doc_type.prefix + '/9999999', headers=headers, status=404)
    client.get(doc_type.prefix + '/9999999?l=es', headers=headers, status=404)


def assert_notified_es(client):
    """Check that a sync. notification was sent for ES, and take it."""
    queue_config = client.registry.queue_config
    queue = queue_config.queue(queue_config.connection)
    assert queue.get() is not None, 'no sync. notification sent for ES'


def _post(client, doc_type, request_body, user, status):
    # without a token: forbidden, then as the given user
    send_json(client, 'post', doc_type.prefix, request_body, status=403)
    return send_json(
        client,
        'post',
        doc_type.prefix,
        request_body,
        headers=auth_headers(username=user),
        status=status,
    )


def _single_error(body):
    assert body.get('status') == 'error'
    errors = body.get('errors')
    assert len(errors) == 1
    return errors[0]


def post_error(client, doc_type, request_body, user='contributor', status=400):
    """Post an invalid document: some errors."""
    body = _post(client, doc_type, request_body, user, status).json
    assert len(errors_of(body)) > 0
    return body


def post_missing_title(client, doc_type, request_body, user='contributor', prefix=''):
    """Post a document without title."""
    body = _post(client, doc_type, request_body, user, 422).json
    errors = errors_of(body)
    assert_required(errors[0], prefix + 'locales.0.title')
    return body


def post_missing_geometry(client, doc_type, request_body):
    """Post a document without geometry."""
    body = _post(client, doc_type, request_body, 'contributor', 400).json
    assert_required(_single_error(body), 'geometry')
    return body


def post_missing_geom(client, doc_type, request_body):
    """Post a document with a geometry without point."""
    body = _post(client, doc_type, request_body, 'contributor', 400).json
    assert_required(_single_error(body), 'geometry.geom')
    return body


def post_wrong_geom_type(client, doc_type, request_body, status=400):
    """Post a document with a wrong geometry type; return the errors."""
    response = _post(client, doc_type, request_body, 'contributor', status)
    return errors_of(response.json)


def post_missing_locales(client, doc_type, request_body):
    """Post a document without locales."""
    body = _post(client, doc_type, request_body, 'contributor', 400).json
    error = _single_error(body)
    assert error.get('description') == 'Required'
    assert error.get('name') == 'locales'
    return body


def post_same_locale_twice(client, doc_type, request_body):
    """Post a document with the same language twice."""
    body = _post(client, doc_type, request_body, 'contributor', 400).json
    error = _single_error(body)
    assert error.get('description') == 'lang "en" is given twice'
    assert error.get('name') == 'locales'
    return body


def post_missing_field(client, doc_type, request_body, field):
    """Post a document without a required field."""
    body = _post(client, doc_type, request_body, 'contributor', 400).json
    error = _single_error(body)
    assert error.get('description') == 'Required'
    assert error.get('name') == field
    return body


def post_non_whitelisted_attribute(
    client, session, doc_type, request_body, user='contributor'
):
    """Post a document with `protected`, which is ignored."""
    body = _post(client, doc_type, request_body, user, 200).json
    document_id = body.get('document_id')
    document = session.get(doc_type.model, document_id)
    # the value for `protected` was ignored
    assert not document.protected
    return (body, document)


def post_missing_content_type(client, doc_type, request_body):
    """Post a document without content type."""
    response = client.post(doc_type.prefix, params=json.dumps(request_body), status=415)

    error = _single_error(response.json)
    assert error.get('location') == 'header'
    assert error.get('name') == 'Content-Type'
    return response.json


def post_success(
    client,
    session,
    doc_type,
    request_body,
    user='contributor',
    validate_with_auth=False,
    skip_validation=False,
):
    """Post a document, then check what was written; return it."""
    headers = auth_headers(username=user)
    body = _post(client, doc_type, request_body, user, 200).json
    if skip_validation:
        document_id = body.get('document_id')
        response = client.get(doc_type.prefix + '/' + str(document_id), status=200)
        doc = session.get(doc_type.model, document_id)
        return response.json, doc
    return validate_document(
        client,
        session,
        doc_type,
        body,
        headers if validate_with_auth else None,
    )


def validate_document(client, session, doc_type, body, headers=None):
    """Check a new document: its first version, archives, ES and cache."""
    document_id = body.get('document_id')
    assert document_id is not None

    response = client.get(
        doc_type.prefix + '/' + str(document_id), headers=headers, status=200
    )
    assert response.content_type == 'application/json'

    body = response.json
    assert body.get('version') is not None
    assert body.get('protected') is False

    # check that the version was created correctly
    doc = session.get(doc_type.model, document_id)
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
    locale = doc.locales[0]
    assert 1 == locale.version
    assert archive_locale.version == locale.version
    assert archive_locale.document_id == document_id
    assert archive_locale.lang == lang

    # check updates to the search index
    assert_notified_es(client)
    sync_es(session)
    search_doc = search_documents[doc_type.type].get(
        id=doc.document_id, index=elasticsearch_config['index']
    )

    assert search_doc['doc_type'] is not None
    assert search_doc['doc_type'] == doc.type

    if isinstance(doc, Route):
        title = locale.title_prefix + ' : ' + locale.title
        assert search_doc['title_en'] == title
    else:
        assert search_doc['title_en'] == locale.title

    cache_version = session.get(CacheVersion, document_id)
    assert cache_version is not None
    assert cache_version.version == 1

    return (body, doc)
