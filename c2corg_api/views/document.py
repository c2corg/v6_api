import logging

from c2corg_api.caching import cache_document_detail, cache_document_listing
from c2corg_api.models.cache_version import update_cache_version, \
    update_cache_version_associations, get_cache_key, get_document_id, \
    get_cache_keys
from c2corg_api.models.image import schema_association_image
from c2corg_api.models.outing import Outing
from c2corg_api.models.topo_map_association import update_maps_for_document, \
    get_maps
from c2corg_api.models.user import User, schema_association_user
from functools import partial

from c2corg_api.models import DBSession
from c2corg_api.models.area import AREA_TYPE, schema_listing_area
from c2corg_api.models.area_association import update_areas_for_document, \
    get_areas
from c2corg_api.models.association import get_associations, \
    create_associations, synchronize_associations
from c2corg_api.models.document import (
    UpdateType, DocumentLocale, ArchiveDocumentLocale, ArchiveDocument,
    ArchiveDocumentGeometry, set_available_langs, get_available_langs)
from c2corg_api.models.document_history import HistoryMetaData, DocumentVersion
from c2corg_api.models.route import schema_association_route
from c2corg_api.models.topo_map import schema_listing_topo_map, \
    MAP_TYPE
from c2corg_api.models.user_profile import UserProfile
from c2corg_api.models.waypoint import schema_association_waypoint
from c2corg_api.search import advanced_search
from c2corg_api.search.notify_sync import notify_es_syncer
from c2corg_api.views import etag_cache
from c2corg_api.views import to_json_dict, set_best_locale
from c2corg_api.views.validation import check_required_fields, \
    check_duplicate_locales
from pyramid.httpexceptions import HTTPNotFound, HTTPConflict, \
    HTTPBadRequest, HTTPForbidden
from sqlalchemy.orm import joinedload, contains_eager, subqueryload, load_only
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.orm.util import with_polymorphic

log = logging.getLogger(__name__)

# the maximum number of documents that can be returned in a request
LIMIT_MAX = 100

# the default limit value (how much documents are returned at once in a
# listing request)
LIMIT_DEFAULT = 30

# the number of recent outings that are included for waypoint and routes
NUM_RECENT_OUTINGS = 10


class DocumentRest(object):

    def __init__(self, request):
        self.request = request

    def _collection_get(self, clazz, schema, doc_type, clazz_locale=None,
                        adapt_schema=None, custom_filter=None,
                        include_areas=True, set_custom_fields=None):
        validated = self.request.validated
        meta_params = {
            'offset': validated.get('offset', 0),
            'limit': min(validated.get('limit', LIMIT_DEFAULT), LIMIT_MAX),
            'lang': validated.get('lang')
        }

        if not custom_filter and \
                advanced_search.contains_search_params(self.request.GET):
            # search with ElasticSearch
            search_documents = advanced_search.get_search_documents(
                self.request.GET, meta_params, doc_type)
        else:
            # if no search parameters, directly load documents from the db
            search_documents = partial(
                self._search_documents_paginated, meta_params)

        return self._get_documents(
            clazz, schema, clazz_locale, adapt_schema, custom_filter,
            include_areas, set_custom_fields, meta_params, search_documents)

    def _get_documents(
            self, clazz, schema, clazz_locale, adapt_schema, custom_filter,
            include_areas, set_custom_fields, meta_params, search_documents):
        lang = meta_params['lang']
        base_query = DBSession.query(clazz).\
            filter(getattr(clazz, 'redirects_to').is_(None))
        base_total_query = DBSession.query(getattr(clazz, 'document_id')).\
            filter(getattr(clazz, 'redirects_to').is_(None))

        if custom_filter:
            base_query = custom_filter(base_query)
            base_total_query = custom_filter(base_total_query)
        base_total_query = add_profile_filter(base_total_query, clazz)
        base_query = add_load_for_profiles(base_query, clazz)

        if clazz == Outing:
            base_query = base_query. \
                order_by(clazz.date_end.desc()). \
                order_by(clazz.document_id.desc())
        else:
            base_query = base_query.order_by(clazz.document_id.desc())

        document_ids, total = search_documents(base_query, base_total_query)
        cache_keys = get_cache_keys(document_ids, lang)

        def get_documents_from_cache_keys(*cache_keys):
            """ This method is called from dogpile.cache with the cache keys
            for the documents that are not cached yet.
            """
            ids = [get_document_id(cache_key) for cache_key in cache_keys]

            docs = self._get_documents_from_ids(
                ids, base_query, clazz, schema, clazz_locale,
                adapt_schema, include_areas, set_custom_fields, lang)

            assert len(cache_keys) == len(docs), \
                'the number of returned documents must match ' + \
                'the number of keys'

            return docs

        # get the documents from the cache or from the database
        documents = cache_document_listing.get_or_create_multi(
            cache_keys, get_documents_from_cache_keys, expiration_time=-1,
            should_cache_fn=lambda v: v is not None)

        return {
            'documents': [doc for doc in documents if doc],
            'total': total
        }

    def _get_documents_from_ids(
            self, document_ids, base_query, clazz, schema, clazz_locale,
            adapt_schema, include_areas, set_custom_fields, lang):
        """ Load the documents for the ids and return them as json dict.
        The returned list contains None values for documents that could not be
        loaded, and the list has the same order has the document id list.
        """
        base_query = add_load_for_locales(base_query, clazz, clazz_locale)
        base_query = base_query.options(joinedload(getattr(clazz, 'geometry')))

        if include_areas:
            base_query = base_query. \
                options(
                    joinedload(getattr(clazz, '_areas')).
                    load_only(
                        'document_id', 'area_type', 'version', 'protected',
                        'type').
                    joinedload('locales').
                    load_only(
                        'lang', 'title',
                        'version')
                )

        documents = self._load_documents(document_ids, clazz, base_query)

        set_available_langs(documents, loaded=True)
        if lang is not None:
            set_best_locale(documents, lang)

        if include_areas:
            self._set_areas_for_documents(documents, lang)

        if set_custom_fields:
            set_custom_fields(documents, lang)

        # make sure the documents are returned in the same order
        document_index = {doc.document_id: doc for doc in documents}
        documents = [document_index.get(id) for id in document_ids]

        return [
            to_json_dict(
                doc,
                schema if not adapt_schema else adapt_schema(schema, doc)
            ) if doc else None for doc in documents
        ]

    def _load_documents(self, document_ids, clazz, base_query):
        """ Load documents given a list of document ids. Note that the
        returned list does not contain the documents in the same order as
        the passed in document id list.
        """
        if not document_ids:
            return []

        documents = base_query. \
            filter(clazz.document_id.in_(document_ids)).\
            all()

        return documents

    def _search_documents_paginated(
            self, meta_params, base_query, base_total_query):
        """Return a batch of document ids with the given `offset` and `limit`.
        """
        offset = meta_params['offset']
        limit = meta_params['limit']
        documents = base_query. \
            options(load_only('document_id', 'type', 'version')). \
            slice(offset, offset + limit). \
            limit(limit). \
            all()
        total = base_total_query.count()

        document_ids = [doc.document_id for doc in documents]

        return document_ids, total

    def _get(self, clazz, schema, clazz_locale=None, adapt_schema=None,
             include_maps=False, include_areas=True,
             set_custom_associations=None):
        id = self.request.validated['id']
        lang = self.request.validated.get('lang')
        editing_view = self.request.GET.get('e', '0') != '0'

        def create_response():
            return self._get_in_lang(
                id, lang, clazz, schema, editing_view, clazz_locale,
                adapt_schema, include_maps, include_areas,
                set_custom_associations)

        if not editing_view:
            cache_key = get_cache_key(id, lang)

            if cache_key:
                # set and check the etag: if the etag value provided in the
                # request equals the current etag, return 'NotModified'
                etag_cache(self.request, cache_key)

                return cache_document_detail.get_or_create(
                    cache_key, create_response, expiration_time=-1)

        # don't cache if requesting a document for editing
        return create_response()

    def _get_in_lang(self, id, lang, clazz, schema, editing_view,
                     clazz_locale=None, adapt_schema=None,
                     include_maps=True, include_areas=True,
                     set_custom_associations=None):
        document = self._get_document(
            clazz, id, clazz_locale=clazz_locale, lang=lang)

        if document.redirects_to:
            return {
                'redirects_to': document.redirects_to,
                'available_langs': get_available_langs(document.redirects_to)
            }

        set_available_langs([document])

        self._set_associations(document, lang, editing_view)

        if not editing_view and set_custom_associations:
            set_custom_associations(document, lang)

        if not editing_view and include_areas:
            self._set_areas(document, lang)

        if include_maps:
            self._set_maps(document, lang)

        if adapt_schema:
            schema = adapt_schema(schema, document)

        return to_json_dict(document, schema)

    def _set_associations(self, document, lang, editing_view):
        linked_docs = get_associations(document, lang, editing_view)

        associations = {}
        for typ, docs in linked_docs.items():
            schema = association_schemas[typ]
            associations[typ] = [
                to_json_dict(d, schema)
                for d in docs
            ]

        document.associations = associations

    def _set_maps(self, document, lang):
        topo_maps = get_maps(document, lang)
        document.maps = [
            to_json_dict(m, schema_listing_topo_map) for m in topo_maps
        ]

    def _set_areas(self, document, lang):
        areas = get_areas(document, lang)
        document.areas = [
            to_json_dict(m, schema_listing_area) for m in areas
        ]

    def _set_areas_for_documents(self, documents, lang):
        for document in documents:
            # expunge is set to False because the parent document of the areas
            # was already disconnected from the session at this point
            set_best_locale(document._areas, lang, expunge=False)

            document.areas = [
                to_json_dict(m, schema_listing_area) for m in document._areas
            ]

    def _collection_post(
            self, schema, before_add=None, after_add=None):
        document_in = self.request.validated
        document = self._create_document(
                document_in, schema, before_add, after_add)
        return {'document_id': document.document_id}

    def _create_document(
            self, document_in, schema, before_add=None, after_add=None):
        user_id = self.request.authenticated_userid

        document = schema.objectify(document_in)
        document.document_id = None

        if before_add:
            before_add(document, user_id=user_id)

        DBSession.add(document)
        DBSession.flush()
        DocumentRest.create_new_version(document, user_id)

        if document.type != AREA_TYPE:
            update_areas_for_document(document, reset=False)

        if document.type != MAP_TYPE:
            update_maps_for_document(document, reset=False)

        if after_add:
            after_add(document, user_id=user_id)

        if document_in.get('associations', None):
            create_associations(document, document_in['associations'], user_id)

        notify_es_syncer(self.request.registry.queue_config)
        return document

    def _put(
            self, clazz, schema, clazz_locale=None, before_update=None,
            after_update=None):
        user_id = self.request.authenticated_userid
        id = self.request.validated['id']
        document_in = \
            schema.objectify(self.request.validated['document'])
        self._check_document_id(id, document_in.document_id)

        # get the current version of the document
        document = self._get_document(clazz, id, clazz_locale=clazz_locale)

        if document.redirects_to:
            raise HTTPBadRequest('can not update merged document')
        if document.protected and not self.request.has_permission('moderator'):
            raise HTTPForbidden('No permission to change a protected document')

        self._check_versions(document, document_in)

        # remember the current version numbers of the document
        old_versions = document.get_versions()

        # update the document with the input document
        document.update(document_in)

        if before_update:
            before_update(document, document_in, user_id=user_id)

        try:
            DBSession.flush()
        except StaleDataError:
            raise HTTPConflict('concurrent modification')

        # when flushing the session, SQLAlchemy automatically updates the
        # version numbers in case attributes have changed. by comparing with
        # the old version numbers, we can check if only figures or only locales
        # have changed.
        (update_types, changed_langs) = document.get_update_type(old_versions)

        if update_types:
            # A new version needs to be created and persisted
            self._update_version(
                document, user_id, self.request.validated['message'],
                update_types,  changed_langs)

            if document.type != AREA_TYPE and UpdateType.GEOM in update_types:
                update_areas_for_document(document, reset=True)

            if document.type != MAP_TYPE and UpdateType.GEOM in update_types:
                update_maps_for_document(document, reset=True)

            if after_update:
                after_update(document, update_types, user_id=user_id)

            update_cache_version(document)

        associations = self.request.validated.get('associations', None)
        if associations:
            added_associations, removed_associations = \
                synchronize_associations(document, associations, user_id)

        if update_types or associations:
            # update search index
            notify_es_syncer(self.request.registry.queue_config)
        if associations and (removed_associations or added_associations):
            update_cache_version_associations(
                added_associations, removed_associations)

        return {}

    def _get_document(self, clazz, id, clazz_locale=None, lang=None):
        """Get a document with either a single locale (if `lang is given)
        or with all locales.
        If no document exists for the given id, a `HTTPNotFound` exception is
        raised.
        """
        if not lang:
            document_query = DBSession. \
                query(clazz). \
                filter(getattr(clazz, 'document_id') == id). \
                options(joinedload('geometry'))
            document_query = add_load_for_locales(
                document_query, clazz, clazz_locale)
            document_query = add_load_for_profiles(document_query, clazz)
            document = document_query.first()
        else:
            locales_type = with_polymorphic(DocumentLocale, clazz_locale) \
                if clazz_locale else DocumentLocale
            locales_attr = getattr(clazz, 'locales')
            locales_type_eager = locales_attr.of_type(clazz_locale) \
                if clazz_locale else locales_attr

            document_query = DBSession. \
                query(clazz). \
                join(locales_type). \
                filter(getattr(clazz, 'document_id') == id). \
                filter(DocumentLocale.lang == lang). \
                options(joinedload('geometry')).\
                options(contains_eager(locales_type_eager, alias=locales_type))
            document_query = add_load_for_profiles(document_query, clazz)
            document = document_query.first()

            if not document:
                # the requested locale might not be available, try to get the
                # document without locales
                document_query = DBSession. \
                    query(clazz). \
                    filter(getattr(clazz, 'document_id') == id). \
                    options(joinedload('geometry'))
                document_query = add_load_for_profiles(document_query, clazz)
                document = document_query.first()

                if document:
                    # explicitly set `locales` to an empty list so that they
                    # are no lazy loaded
                    document.locales = []
                    # also detach the document from the session, so that the
                    # empty list is not persisted
                    DBSession.expunge(document)

        if not document:
            raise HTTPNotFound('document not found')

        return document

    @staticmethod
    def create_new_version(document, user_id):
        assert user_id
        archive = document.to_archive()
        archive_locales = document.get_archive_locales()
        archive_geometry = document.get_archive_geometry()

        meta_data = HistoryMetaData(comment='creation', user_id=user_id)
        versions = []
        for locale in archive_locales:
            version = DocumentVersion(
                document_id=document.document_id,
                lang=locale.lang,
                document_archive=archive,
                document_locales_archive=locale,
                document_geometry_archive=archive_geometry,
                history_metadata=meta_data
            )
            versions.append(version)

        DBSession.add(archive)
        DBSession.add_all(archive_locales)
        DBSession.add(meta_data)
        DBSession.add_all(versions)
        DBSession.flush()

    def _update_version(self, document, user_id, comment, update_types,
                        changed_langs):
        assert user_id
        assert update_types

        meta_data = HistoryMetaData(comment=comment, user_id=user_id)
        archive = self._get_document_archive(document, update_types)
        geometry_archive = \
            self._get_geometry_archive(document, update_types)

        langs = \
            self._get_langs_to_update(document, update_types, changed_langs)
        locale_versions = []
        for lang in langs:
            locale = document.get_locale(lang)
            locale_archive = self._get_locale_archive(locale, changed_langs)

            version = DocumentVersion(
                document_id=document.document_id,
                lang=locale.lang,
                document_archive=archive,
                document_geometry_archive=geometry_archive,
                document_locales_archive=locale_archive,
                history_metadata=meta_data
            )
            locale_versions.append(version)

        DBSession.add(archive)
        DBSession.add(meta_data)
        DBSession.add_all(locale_versions)
        DBSession.flush()

    def _get_document_archive(self, document, update_types):
        if (UpdateType.FIGURES in update_types):
            # the document has changed, create a new archive version
            archive = document.to_archive()
        else:
            # the document has not changed, load the previous archive version
            archive = DBSession.query(ArchiveDocument). \
                filter(
                    ArchiveDocument.version == document.version,
                    ArchiveDocument.document_id == document.document_id). \
                one()
        return archive

    def _get_geometry_archive(self, document, update_types):
        if not document.geometry:
            return None
        elif (UpdateType.GEOM in update_types):
            # the geometry has changed, create a new archive version
            archive = document.geometry.to_archive()
        else:
            # the geometry has not changed, load the previous archive version
            archive = DBSession.query(ArchiveDocumentGeometry). \
                filter(
                    ArchiveDocumentGeometry.version ==
                    document.geometry.version,
                    ArchiveDocumentGeometry.document_id ==
                    document.document_id
                ). \
                one()
        return archive

    def _get_langs_to_update(self, document, update_types, changed_langs):
        if UpdateType.GEOM not in update_types and \
                UpdateType.FIGURES not in update_types:
            # if the figures or geometry have no been changed, only update the
            # locales that have been changed
            return changed_langs
        else:
            # if the figures or geometry have been changed, update all locales
            return [locale.lang for locale in document.locales]

    def _get_locale_archive(self, locale, changed_langs):
        if locale.lang in changed_langs:
            # create new archive version for this locale
            locale_archive = locale.to_archive()
        else:
            # the locale has not changed, use the old archive version
            locale_archive = DBSession.query(ArchiveDocumentLocale). \
                filter(
                    ArchiveDocumentLocale.version == locale.version,
                    ArchiveDocumentLocale.document_id == locale.document_id,
                    ArchiveDocumentLocale.lang == locale.lang). \
                one()
        return locale_archive

    def _check_document_id(self, id, document_id):
        """Checks that the id given in the URL ("/waypoints/{id}") matches
        the document_id given in the request body.
        """
        if id != document_id:
            raise HTTPBadRequest(
                'id in the url does not match document_id in request body')

    def _check_versions(self, document, document_in):
        """Check that the passed-in document, geometry and all passed-in
        locales have the same version as the current document, geometry and
        locales in the database.
        If not (that is the document has changed), a `HTTPConflict` exception
        is raised.
        """
        if document.version != document_in.version:
            raise HTTPConflict('version of document has changed')
        for locale_in in document_in.locales:
            locale = document.get_locale(locale_in.lang)
            if locale:
                if locale.version != locale_in.version:
                    raise HTTPConflict(
                        'version of locale \'%s\' has changed'
                        % locale.lang)
        if document.geometry and document_in.geometry:
            if document.geometry.version != document_in.geometry.version:
                raise HTTPConflict('version of geometry has changed')


def validate_document_for_type(document, request, fields, type_field,
                               valid_type_values, updating):
    """Checks that all required fields are given.
    """
    document_type = document.get(type_field)

    if not document_type:
        # can't do the validation without the type (an error was already added
        # when validating the Colander schema)
        return

    if type_field == 'activities':
        # for routes the required fields depend on the assigned activities of
        # a route. but because currently all activities have the same required
        # fields, we can simply take the required fields of the first
        # activity. if this is going to change in the future the fields for
        # activities would have to be taken into account.
        document_type = document_type[0]

    if document_type not in valid_type_values:
        request.errors.add(
            'body', type_field, 'invalid value: %s' % document_type)
        return

    fields_req = fields.get(document_type)['required']
    validate_document(document, request, fields_req, updating)


def validate_document(document, request, fields, updating):
    """Checks that all required fields are given.
    """
    check_required_fields(document, fields, request, updating)
    check_duplicate_locales(document, request)


def make_validator_create(
        fields, type_field=None, valid_type_values=None):
    """Returns a validator function used for the creation of documents.
    """
    if type_field is None or valid_type_values is None:
        def f(request):
            document = request.validated
            validate_document(document, request, fields, updating=False)
    else:
        def f(request):
            document = request.validated
            validate_document_for_type(
                document, request, fields, type_field, valid_type_values,
                updating=False)
    return f


def make_validator_update(fields, type_field=None, valid_type_values=None):
    """Returns a validator function used for updating documents.
    """
    if type_field is None or valid_type_values is None:
        def f(request):
            document = request.validated.get('document')
            if document:
                validate_document(document, request, fields, updating=True)
    else:
        def f(request):
            document = request.validated.get('document')
            if document:
                validate_document_for_type(
                    document, request, fields, type_field, valid_type_values,
                    updating=True)
    return f


def make_schema_adaptor(adapt_schema_for_type, type_field, field_list_type):
    """Returns a function which adapts a base schema to a specific document
    type, e.g. it returns a function which turns the base schema for waypoints
    into a schema which contains only the fields for the waypoint type
    "summit".
    """
    def adapt_schema(_base_schema, document):
        return adapt_schema_for_type(
            getattr(document, type_field), field_list_type)
    return adapt_schema


def get_all_fields(fields, activities, field_list_type):
    """Returns all fields needed for the given list of activities.
    """
    fields_list = [
        fields.get(activity).get(field_list_type) for activity in activities
    ]
    # turn a list of lists [['a', 'b'], ['b', 'c'], ['d']] into a flat set
    # ['a', 'b', 'c', 'd']
    return set(sum(fields_list, []))


def add_load_for_profiles(document_query, clazz):
    if clazz == UserProfile:
        # for profiles load username/name together from the associated user
        document_query = add_profile_filter(document_query, clazz). \
            options(contains_eager('user'))
    return document_query


def add_profile_filter(document_query, clazz):
    if clazz == UserProfile:
        # make sure only confirmed accounts are returned
        document_query = document_query. \
            join(User). \
            filter(User.email_validated)
    return document_query


def add_load_for_locales(
        base_query, clazz, clazz_locale):
    if clazz_locale:
        return base_query.options(
            subqueryload(getattr(clazz, 'locales').of_type(clazz_locale)))
    else:
        return base_query.options(subqueryload(getattr(clazz, 'locales')))

association_schemas = {
    'waypoints': schema_association_waypoint,
    'waypoint_children': schema_association_waypoint,
    'routes': schema_association_route,
    'users': schema_association_user,
    'images': schema_association_image
}
