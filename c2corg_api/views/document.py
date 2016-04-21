from c2corg_api.models import DBSession
from c2corg_api.models.area import AREA_TYPE, schema_listing_area
from c2corg_api.models.area_association import update_areas_for_document, \
    get_areas
from c2corg_api.models.association import get_associations
from c2corg_api.models.document import (
    UpdateType, DocumentLocale, ArchiveDocumentLocale, ArchiveDocument,
    ArchiveDocumentGeometry, set_available_langs, get_available_langs)
from c2corg_api.models.document_history import HistoryMetaData, DocumentVersion
from c2corg_api.models.route import schema_association_route
from c2corg_api.models.topo_map import get_maps, schema_listing_topo_map
from c2corg_api.models.user_profile import UserProfile
from c2corg_api.models.waypoint import schema_association_waypoint
from c2corg_api.search.notify_sync import notify_es_syncer
from c2corg_api.views import cors_policy
from c2corg_api.views import to_json_dict, to_seconds, set_best_locale
from c2corg_api.views.validation import check_required_fields, \
    check_duplicate_locales, validate_id, validate_lang
from cornice.resource import resource, view
from pyramid.httpexceptions import HTTPNotFound, HTTPConflict, \
    HTTPBadRequest, HTTPForbidden
from sqlalchemy.orm import joinedload, contains_eager
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.sql.expression import literal_column, union

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

    def _collection_get(self, clazz, schema, clazz_locale=None,
                        adapt_schema=None, custom_filter=None,
                        include_areas=True, set_custom_fields=None):
        return self._paginate(
            clazz, schema, clazz_locale, adapt_schema, custom_filter,
            include_areas, set_custom_fields)

    def _paginate(
            self, clazz, schema, clazz_locale, adapt_schema, custom_filter,
            include_areas, set_custom_fields):
        validated = self.request.validated

        base_query = DBSession.query(clazz).\
            filter(getattr(clazz, 'redirects_to').is_(None))
        base_total_query = DBSession.query(getattr(clazz, 'document_id')).\
            filter(getattr(clazz, 'redirects_to').is_(None))

        if custom_filter:
            base_query = custom_filter(base_query)
            base_total_query = custom_filter(base_total_query)

        base_query = add_load_for_locales(base_query, clazz, clazz_locale)
        base_query = base_query. \
            options(joinedload(getattr(clazz, 'geometry'))). \
            order_by(clazz.document_id.desc())
        base_query = add_load_for_profiles(base_query, clazz)

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

        documents, total = self._paginate_offset(base_query, base_total_query)

        set_available_langs(documents, loaded=True)
        if validated.get('lang') is not None:
            set_best_locale(documents, validated.get('lang'))

        if include_areas:
            self._set_areas_for_documents(documents, validated.get('lang'))

        if set_custom_fields:
            set_custom_fields(documents, validated.get('lang'))

        return {
            'documents': [
                to_json_dict(
                    doc,
                    schema if not adapt_schema else adapt_schema(schema, doc)
                ) for doc in documents
            ],
            'total': total
        }

    def _paginate_offset(self, base_query, base_total_query):
        """Return a batch of documents with the given `offset` and `limit`.
        """
        validated = self.request.validated
        offset = validated['offset'] if 'offset' in validated else 0
        limit = min(
            validated['limit'] if 'limit' in validated else LIMIT_DEFAULT,
            LIMIT_MAX)

        documents = base_query. \
            slice(offset, offset + limit). \
            limit(limit). \
            all()
        total = base_total_query.count()

        return documents, total

    def _get(self, clazz, schema, clazz_locale=None, adapt_schema=None,
             include_maps=False, include_areas=True,
             set_custom_associations=None):
        id = self.request.validated['id']
        lang = self.request.validated.get('lang')
        return self._get_in_lang(
            id, lang, clazz, schema, clazz_locale, adapt_schema, include_maps,
            include_areas, set_custom_associations)

    def _get_in_lang(self, id, lang, clazz, schema,
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

        include_associations = self.request.GET.get('a', '1') == '1'
        if include_associations:
            self._set_associations(document, lang)
            if set_custom_associations:
                set_custom_associations(document, lang)

            if include_areas:
                self._set_areas(document, lang)

        if include_maps:
            self._set_maps(document, lang)

        if adapt_schema:
            schema = adapt_schema(schema, document)

        return to_json_dict(document, schema)

    def _set_associations(self, document, lang):
        linked_waypoints, linked_routes = get_associations(document, lang)
        document.associations = {
            'waypoints': [
                to_json_dict(wp, schema_association_waypoint)
                for wp in linked_waypoints
            ],
            'routes': [
                to_json_dict(r, schema_association_route)
                for r in linked_routes
            ]
        }

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
            self, schema, before_add=None, after_add=None,
            document_field=None):
        user_id = self.request.authenticated_userid
        document_in = self.request.validated if document_field is None else \
            self.request.validated[document_field]
        document = schema.objectify(document_in)
        document.document_id = None

        if before_add:
            before_add(document, user_id=user_id)

        DBSession.add(document)
        DBSession.flush()
        DocumentRest.create_new_version(document, user_id)

        if document.type != AREA_TYPE:
            update_areas_for_document(document, reset=False)

        if after_add:
            after_add(document, user_id=user_id)

        notify_es_syncer(self.request.registry.queue_config)

        return {'document_id': document.document_id}

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

            if after_update:
                after_update(document, update_types, user_id=user_id)

            # And the search updated
            notify_es_syncer(self.request.registry.queue_config)

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
            document_query = DBSession. \
                query(clazz). \
                join(getattr(clazz, 'locales')). \
                filter(getattr(clazz, 'document_id') == id). \
                filter(DocumentLocale.lang == lang). \
                options(joinedload('geometry'))
            document_query = add_load_for_locales(
                document_query, clazz, clazz_locale,
                loading_method=contains_eager)
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

    def _get_version(self, clazz, locale_clazz, schema, adapt_schema=None):
        id = self.request.validated['id']
        lang = self.request.validated['lang']
        version_id = self.request.validated['version_id']

        version = DBSession.query(DocumentVersion) \
            .options(joinedload('history_metadata').joinedload('user')) \
            .options(joinedload(
                DocumentVersion.document_archive.of_type(clazz))) \
            .options(joinedload(
                DocumentVersion.document_locales_archive.of_type(
                    locale_clazz))) \
            .options(joinedload(DocumentVersion.document_geometry_archive)) \
            .filter(DocumentVersion.id == version_id) \
            .filter(DocumentVersion.document_id == id) \
            .filter(DocumentVersion.lang == lang) \
            .first()
        if version is None:
            raise HTTPNotFound('invalid version')

        archive_document = version.document_archive
        archive_document.geometry = version.document_geometry_archive
        archive_document.locales = [version.document_locales_archive]

        if adapt_schema:
            schema = adapt_schema(schema, archive_document)

        previous_version_id, next_version_id = get_neighbour_version_ids(
            version_id, id, lang
        )

        return {
            'document': to_json_dict(archive_document, schema),
            'version': self._serialize_version(version),
            'previous_version_id': previous_version_id,
            'next_version_id': next_version_id,
        }

    def _serialize_version(self, version):
        return {
            'version_id': version.id,
            'user_id': version.history_metadata.user_id,
            'username': version.history_metadata.user.username,
            'comment': version.history_metadata.comment,
            'written_at': to_seconds(version.history_metadata.written_at)
        }


def get_neighbour_version_ids(version_id, document_id, lang):
    """
    Get the previous and next version for a version of a document with a
    specific language.
    """
    next_version = DBSession \
        .query(
            DocumentVersion.id.label('id'),
            literal_column('1').label('t')) \
        .filter(DocumentVersion.id > version_id) \
        .filter(DocumentVersion.document_id == document_id) \
        .filter(DocumentVersion.lang == lang) \
        .order_by(DocumentVersion.id) \
        .limit(1) \
        .subquery()

    previous_version = DBSession \
        .query(
            DocumentVersion.id.label('id'),
            literal_column('-1').label('t')) \
        .filter(DocumentVersion.id < version_id) \
        .filter(DocumentVersion.document_id == document_id) \
        .filter(DocumentVersion.lang == lang) \
        .order_by(DocumentVersion.id.desc()) \
        .limit(1) \
        .subquery()

    query = DBSession \
        .query('id', 't') \
        .select_from(union(
            next_version.select(), previous_version.select()))

    previous_version_id = None
    next_version_id = None
    for version, typ in query:
        if typ == -1:
            previous_version_id = version
        else:
            next_version_id = version

    return previous_version_id, next_version_id


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
        fields, type_field=None, valid_type_values=None, document_field=None):
    """Returns a validator function used for the creation of documents.
    """
    if type_field is None or valid_type_values is None:
        def f(request):
            document = request.validated if document_field is None else \
                request.validated.get(document_field, {})
            validate_document(document, request, fields, updating=False)
    else:
        def f(request):
            document = request.validated if document_field is None else \
                request.validated.get(document_field, {})
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
        document_query = document_query.options(joinedload('user'))
    return document_query


def add_load_for_locales(
        base_query, clazz, clazz_locale, loading_method=joinedload):
    if clazz_locale:
        return base_query.options(
            loading_method(getattr(clazz, 'locales').of_type(clazz_locale)))
    else:
        return base_query.options(loading_method(getattr(clazz, 'locales')))


@resource(path='/document/{id}/history/{lang}', cors_policy=cors_policy)
class HistoryDocumentRest(DocumentRest):
    """Unique class for returning history of a document.
    """

    @view(validators=[validate_id, validate_lang])
    def get(self):
        id = self.request.validated['id']
        lang = self.request.validated['lang']

        # FIXME conditional permission check (when outings implemented)
        # is_outing = DBSession.query(Outing) \
        #       .filter(Outing.document_id == id).count()
        # if is_outing > 0:
        #    # validate permission (authenticated + associated)
        #    # return 403 if not correct

        title = DBSession.query(DocumentLocale.title) \
            .filter(DocumentLocale.document_id == id) \
            .filter(DocumentLocale.lang == lang) \
            .first()

        if not title:
            raise HTTPNotFound('no locale document for ' + lang)

        versions = DBSession.query(DocumentVersion) \
            .options(joinedload('history_metadata').joinedload('user')) \
            .filter(DocumentVersion.document_id == id) \
            .filter(DocumentVersion.lang == lang) \
            .order_by(DocumentVersion.id) \
            .all()

        return {
            'title': title.title,
            'versions': [self._serialize_version(v) for v in versions]
        }
