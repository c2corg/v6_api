import logging

from c2corg_api.caching import cache_document_detail, cache_document_cooked
from c2corg_api.models import DBSession
from c2corg_api.models.area import AREA_TYPE, schema_listing_area
from c2corg_api.models.area_association import update_areas_for_document, \
    get_areas
from c2corg_api.models.association import create_associations, \
    synchronize_associations
from c2corg_api.models.cache_version import update_cache_version, \
    update_cache_version_associations, get_cache_key
from c2corg_api.models.document import (
    UpdateType, DocumentLocale, ArchiveDocumentLocale, ArchiveDocument,
    ArchiveDocumentGeometry, set_available_langs, get_available_langs)
from c2corg_api.models.document_history import HistoryMetaData, DocumentVersion
from c2corg_api.models.feed import update_feed_document_create, \
    update_feed_document_update
from c2corg_api.models.outing import OUTING_TYPE
from c2corg_api.models.topo_map import schema_listing_topo_map, \
    MAP_TYPE
from c2corg_api.models.topo_map_association import update_maps_for_document, \
    get_maps
from c2corg_api.models.document_views import DocumentViews

from c2corg_api.search import advanced_search
from c2corg_api.search.notify_sync import notify_es_syncer
from c2corg_api.views import etag_cache, set_best_locale
from c2corg_api.views import to_json_dict
import c2corg_api.views.document_associations as doc_associations
from c2corg_api.views.document_listings import add_load_for_locales, \
    add_load_for_profiles, get_documents
from c2corg_api.views.validation import check_required_fields, \
    check_duplicate_locales, association_permission_checker, \
    association_permission_removal_checker

from functools import partial

from c2corg_api.caching import get_or_create
from pyramid.httpexceptions import HTTPNotFound, HTTPConflict, \
    HTTPBadRequest, HTTPForbidden
from sqlalchemy.orm import joinedload, contains_eager, load_only
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

# page offset limit by ElasticSearch
ES_MAX_RESULT_WINDOW = 10000


class DocumentRest(object):

    def __init__(self, request):
        self.request = request

    # TODO: remove doc_type, it's in documents_config
    def _collection_get(self, doc_type, documents_config):
        validated = self.request.validated
        meta_params = {
            'offset': validated.get('offset', 0),
            'limit': min(validated.get('limit', LIMIT_DEFAULT), LIMIT_MAX),
            'lang': validated.get('lang')
        }

        if meta_params['offset'] + meta_params['limit'] > ES_MAX_RESULT_WINDOW:
            # ES does not process requests where offset + limit is greater
            # than 10000, see:
            # https://www.elastic.co/guide/en/elasticsearch/reference/master/search-request-from-size.html
            raise HTTPBadRequest('offset + limit greater than 10000')

        if advanced_search.contains_search_params(self.request.GET):
            # search with ElasticSearch
            search_documents = advanced_search.get_search_documents(
                self.request.GET, meta_params, doc_type)
        else:
            # if no search parameters, directly load documents from the db
            search_documents = partial(
                self._search_documents_paginated, meta_params)

        return get_documents(
            documents_config, meta_params, search_documents)

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

    def increment_views(self,document_id):
        document_views = DBSession.query(DocumentViews) \
            .filter(DocumentViews.document_id == document_id) \
            .first()
        if document_views:
            document_views.view_count = DocumentViews.view_count + 1 
        else:
            views = DocumentViews(
                    document_id=document_id,
                    view_count=1
                )
            DBSession.add(views)

    def _get(self, document_config, schema, clazz_locale=None,
             adapt_schema=None, include_maps=False, include_areas=True,
             set_custom_associations=None, set_custom_fields=None,
             custom_cache_key=None):
        id = self.request.validated['id']
        lang = self.request.validated.get('lang')
        editing_view = self.request.GET.get('e', '0') != '0'
        cook = self.request.validated.get('cook')

        if cook and lang:
            raise HTTPBadRequest(
                "You can't use cook service with explicit lang query"
            )

        if cook and editing_view:
            raise HTTPBadRequest(
                "You can't use cook service with edition mode"
            )

        if cook:
            lang = cook

        cache = cache_document_cooked if cook else cache_document_detail
        self.increment_views(id)
        def create_response():
            return self._get_in_lang(
                id, lang, document_config.clazz, schema, editing_view,
                clazz_locale, adapt_schema, include_maps, include_areas,
                set_custom_associations, set_custom_fields,
                cook_locale=cook)

        if not editing_view:
            cache_key = get_cache_key(
                id,
                lang,
                document_type=document_config.document_type,
                custom_cache_key=custom_cache_key)

            if cache_key:
                # set and check the etag: if the etag value provided in the
                # request equals the current etag, return 'NotModified'
                etag_cache(self.request, cache_key)

                return get_or_create(cache, cache_key, create_response)

        # don't cache if requesting a document for editing
        return create_response()

    def _get_in_lang(self, id, lang, clazz, schema, editing_view,
                     clazz_locale=None, adapt_schema=None,
                     include_maps=True, include_areas=True,
                     set_custom_associations=None, set_custom_fields=None,
                     cook_locale=False):

        if cook_locale:
            document = self._get_document_for_cooking(
                clazz, id, clazz_locale=clazz_locale, lang=lang
            )
        else:
            document = self._get_document(
                clazz, id, clazz_locale=clazz_locale, lang=lang
            )

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

        if set_custom_fields:
            set_custom_fields(document)

        if adapt_schema:
            schema = adapt_schema(schema, document)

        return to_json_dict(
            document,
            schema,
            with_special_locales_attrs=True,
            cook_locale=cook_locale
        )

    def _set_associations(self, document, lang, editing_view):
        document.associations = doc_associations.get_associations(
            document, lang, editing_view)

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

    def _collection_post(
            self, schema, before_add=None, after_add=None,
            allow_anonymous=False):
        document_in = self.request.validated
        document = self._create_document(
                document_in, schema, before_add, after_add, allow_anonymous)
        return {'document_id': document.document_id}

    def _create_document(
            self, document_in, schema, before_add=None, after_add=None,
            allow_anonymous=False):
        if allow_anonymous and document_in.get('anonymous') and \
           self.request.registry.anonymous_user_id:
            user_id = self.request.registry.anonymous_user_id
        else:
            user_id = self.request.authenticated_userid

        document = schema.objectify(document_in)
        document.document_id = None

        if before_add:
            before_add(document, user_id)

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
            check_association = association_permission_checker(
                self.request, skip_outing_check=document.type == OUTING_TYPE)

            added_associations = create_associations(
                document, document_in['associations'], user_id,
                check_association=check_association)
            update_cache_version_associations(
                added_associations, [], document.document_id)

        update_feed_document_create(document, user_id)

        notify_es_syncer(self.request.registry.queue_config)
        return document

    def _put(
            self, clazz, schema, clazz_locale=None, before_update=None,
            after_update=None):
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

        DocumentRest.update_document(document, document_in, self.request,
                                     before_update, after_update)

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
    def _get_document_for_cooking(clazz, document_id, lang, clazz_locale=None):
        """Get a document with a single locale
        this locale may not be the one requested, if this one doesn't exists
        in this case, the lang returned is given by lang_priority
        """

        document_query = DBSession. \
            query(clazz). \
            filter(getattr(clazz, 'document_id') == document_id). \
            options(joinedload('geometry'))
        document_query = add_load_for_locales(
            document_query, clazz, clazz_locale)
        document_query = add_load_for_profiles(document_query, clazz)
        document = document_query.first()

        if not document:
            raise HTTPNotFound('document not found')

        set_best_locale([document], lang)

        return document

    @staticmethod
    def update_document(
            document, document_in, request,
            before_update=None, after_update=None, manage_versions=None):
        user_id = request.authenticated_userid

        # remember the current version numbers of the document
        old_versions = document.get_versions()

        if before_update:
            before_update(document, document_in)

        # update the document with the input document
        document.update(document_in)

        if manage_versions:
            manage_versions(document, old_versions)

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
            DocumentRest.update_version(
                document, user_id, request.validated['message'],
                update_types, changed_langs)

            if document.type != AREA_TYPE and UpdateType.GEOM in update_types:
                update_areas_for_document(document, reset=True)

            if document.type != MAP_TYPE and UpdateType.GEOM in update_types:
                update_maps_for_document(document, reset=True)

            if after_update:
                after_update(document, update_types, user_id=user_id)

            update_cache_version(document)

        associations = request.validated.get('associations', None)
        if associations:
            check_association_add = \
                association_permission_checker(request)
            check_association_remove = \
                association_permission_removal_checker(request)

            added_associations, removed_associations = \
                synchronize_associations(
                    document, associations, user_id,
                    check_association_add=check_association_add,
                    check_association_remove=check_association_remove)

        if update_types or associations:
            # update search index
            notify_es_syncer(request.registry.queue_config)
            update_feed_document_update(document, user_id, update_types)
        if associations and (removed_associations or added_associations):
            update_cache_version_associations(
                added_associations, removed_associations)

        return update_types

    @staticmethod
    def create_new_version(document, user_id, written_at=None):
        assert user_id
        archive = document.to_archive()
        archive_locales = document.get_archive_locales()
        archive_geometry = document.get_archive_geometry()

        meta_data = HistoryMetaData(comment='creation', user_id=user_id,
                                    written_at=written_at)
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

    @staticmethod
    def update_version(
            document, user_id, comment, update_types, changed_langs):
        assert user_id
        assert update_types

        meta_data = HistoryMetaData(comment=comment, user_id=user_id)
        archive = DocumentRest._get_document_archive(document, update_types)
        geometry_archive = \
            DocumentRest._get_geometry_archive(document, update_types)

        langs = DocumentRest._get_langs_to_update(
            document, update_types, changed_langs)
        locale_versions = []
        for lang in langs:
            locale = document.get_locale(lang)
            locale_archive = DocumentRest._get_locale_archive(
                locale, changed_langs)

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

    @staticmethod
    def _get_document_archive(document, update_types):
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

    @staticmethod
    def _get_geometry_archive(document, update_types):
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

    @staticmethod
    def _get_langs_to_update(document, update_types, changed_langs):
        if UpdateType.GEOM not in update_types and \
                UpdateType.FIGURES not in update_types:
            # if the figures or geometry have no been changed, only update the
            # locales that have been changed
            return changed_langs
        else:
            # if the figures or geometry have been changed, update all locales
            return [locale.lang for locale in document.locales]

    @staticmethod
    def _get_locale_archive(locale, changed_langs):
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
        def f(request, **kwargs):
            document = request.validated
            if document:
                validate_document(document, request, fields, updating=False)
    else:
        def f(request, **kwargs):
            document = request.validated
            if document:
                validate_document_for_type(
                    document, request, fields, type_field, valid_type_values,
                    updating=False)
    return f


def make_validator_update(fields, type_field=None, valid_type_values=None):
    """Returns a validator function used for updating documents.
    """
    if type_field is None or valid_type_values is None:
        def f(request, **kwargs):
            document = request.validated.get('document')
            if document:
                validate_document(document, request, fields, updating=True)
    else:
        def f(request, **kwargs):
            document = request.validated.get('document')
            if document:
                validate_document_for_type(
                    document, request, fields, type_field, valid_type_values,
                    updating=True)
    return f
