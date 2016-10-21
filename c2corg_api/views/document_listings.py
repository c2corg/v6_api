from c2corg_api.caching import cache_document_listing
from c2corg_api.models import DBSession
from c2corg_api.models.area import schema_listing_area
from c2corg_api.models.cache_version import get_document_id, \
    get_cache_keys
from c2corg_api.models.document import (
    set_available_langs)
from c2corg_api.models.outing import Outing
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import UserProfile
from c2corg_api.views import to_json_dict, set_best_locale
from sqlalchemy.orm import joinedload, contains_eager, subqueryload, load_only


def get_documents_for_ids(document_ids, lang, documents_config, total=None):
    def search_documents(_, __):
        return document_ids, total

    return get_documents(
        documents_config, {'lang': lang}, search_documents)


def get_documents(documents_config, meta_params, search_documents):
    lang = meta_params['lang']
    base_query = DBSession.query(documents_config.clazz). \
        filter(getattr(documents_config.clazz, 'redirects_to').is_(None))
    base_total_query = DBSession. \
        query(getattr(documents_config.clazz, 'document_id')). \
        filter(getattr(documents_config.clazz, 'redirects_to').is_(None))

    base_total_query = add_profile_filter(
        base_total_query, documents_config.clazz)
    base_query = add_load_for_profiles(base_query, documents_config.clazz)

    if documents_config.clazz == Outing:
        base_query = base_query. \
            order_by(documents_config.clazz.date_end.desc()). \
            order_by(documents_config.clazz.document_id.desc())
    else:
        base_query = base_query.order_by(
            documents_config.clazz.document_id.desc())

    document_ids, total = search_documents(base_query, base_total_query)
    cache_keys = get_cache_keys(
        document_ids, lang, documents_config.document_type)

    def get_documents_from_cache_keys(*cache_keys):
        """ This method is called from dogpile.cache with the cache keys
        for the documents that are not cached yet.
        """
        ids = [get_document_id(cache_key) for cache_key in cache_keys]

        docs = _get_documents_from_ids(
            ids, base_query, documents_config, lang)

        assert len(cache_keys) == len(docs), \
            'the number of returned documents must match ' + \
            'the number of keys'

        return docs

    # get the documents from the cache or from the database
    documents = cache_document_listing.get_or_create_multi(
        cache_keys, get_documents_from_cache_keys, expiration_time=-1,
        should_cache_fn=lambda v: v is not None)

    documents = [doc for doc in documents if doc]
    total = total if total is not None else len(documents)

    return {
        'documents': documents,
        'total': total
    }


def _get_documents_from_ids(
        document_ids, base_query, documents_config, lang):
    """ Load the documents for the ids and return them as json dict.
    The returned list contains None values for documents that could not be
    loaded, and the list has the same order has the document id list.
    """
    base_query = base_query.options(
        load_only(*documents_config.get_load_only_fields())
    )
    base_query = add_load_for_locales(
        base_query, documents_config.clazz, documents_config.clazz_locale,
        documents_config.get_load_only_fields_locales())

    if len(documents_config.get_load_only_fields_geometry()) > 1:
        # only load the geometry if the fields list contains other columns than
        # 'version'
        base_query = base_query.options(
            joinedload(getattr(documents_config.clazz, 'geometry')).
            load_only(*documents_config.get_load_only_fields_geometry())
        )

    if documents_config.include_areas:
        base_query = base_query. \
            options(
                joinedload(getattr(documents_config.clazz, '_areas')).
                load_only(
                    'document_id', 'area_type', 'version', 'protected',
                    'type').
                joinedload('locales').
                load_only(
                    'lang', 'title', 'version')
            )

    documents = _load_documents(
        document_ids, documents_config.clazz, base_query)

    set_available_langs(documents, loaded=True)
    if lang is not None:
        set_best_locale(documents, lang)

    if documents_config.include_areas:
        _set_areas_for_documents(documents, lang)

    if documents_config.set_custom_fields:
        documents_config.set_custom_fields(documents, lang)

    # make sure the documents are returned in the same order
    document_index = {doc.document_id: doc for doc in documents}
    documents = [document_index.get(id) for id in document_ids]

    return [
        to_json_dict(
            doc,
            documents_config.schema if not documents_config.adapt_schema
            else documents_config.adapt_schema(
                documents_config.schema, doc)
        ) if doc else None for doc in documents
        ]


def _load_documents(document_ids, clazz, base_query):
    """ Load documents given a list of document ids. Note that the
    returned list does not contain the documents in the same order as
    the passed in document id list.
    """
    if not document_ids:
        return []

    documents = base_query. \
        filter(clazz.document_id.in_(document_ids)). \
        all()

    return documents


def add_load_for_profiles(document_query, clazz):
    if clazz == UserProfile:
        # for profiles load names together from the associated user
        document_query = add_profile_filter(document_query, clazz). \
            options(contains_eager('user').load_only(
                User.id, User.name, User.forum_username))
    return document_query


def add_profile_filter(document_query, clazz):
    if clazz == UserProfile:
        # make sure only confirmed accounts are returned
        document_query = document_query. \
            join(User). \
            filter(User.email_validated)
    return document_query


def add_load_for_locales(
        base_query, clazz, clazz_locale, load_only_fields=None):
    if clazz_locale:
        locales_load = subqueryload(
            getattr(clazz, 'locales').of_type(clazz_locale))
    else:
        locales_load = subqueryload(getattr(clazz, 'locales'))

    if load_only_fields:
        locales_load = locales_load.load_only(*load_only_fields)

    return base_query.options(locales_load)


def _set_areas_for_documents(documents, lang):
    for document in documents:
        # expunge is set to False because the parent document of the areas
        # was already disconnected from the session at this point
        set_best_locale(document._areas, lang, expunge=False)

        document.areas = [
            to_json_dict(m, schema_listing_area) for m in document._areas
        ]
