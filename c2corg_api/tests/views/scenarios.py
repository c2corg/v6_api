"""Shared test scenarios of the document services, as plain functions."""

# Each scenario calls the API with the given test client and checks the
# answer. It takes the `DocType` of the documents under test: the URL prefix,
# the document type and the models used to check what was written.

import urllib.parse
from collections import Counter
from dataclasses import dataclass

from dateutil import parser as datetime_parser
from dogpile.cache.api import NO_VALUE

from c2corg_api.caching import cache_document_detail
from c2corg_api.models.cache_version import get_cache_key
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import UserProfile
from c2corg_api.tests import global_tokens


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
