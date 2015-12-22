from pyramid.httpexceptions import HTTPNotFound, HTTPConflict, HTTPBadRequest
from sqlalchemy.orm import joinedload, contains_eager
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.sql.expression import literal_column, union
from c2corg_api.models import DBSession
from c2corg_api.models.document import (
    UpdateType, DocumentLocale, ArchiveDocumentLocale, ArchiveDocument,
    ArchiveDocumentGeometry, set_available_cultures)
from c2corg_api.models.document_history import HistoryMetaData, DocumentVersion
from c2corg_api.search.sync import sync_search_index
from c2corg_api.views import to_json_dict, to_seconds
from c2corg_api.views.validation import check_required_fields, \
    check_duplicate_locales, validate_id, validate_lang

from cornice.resource import resource, view
from c2corg_api.views import cors_policy

# the maximum number of documents that can be returned in a request
LIMIT_MAX = 100

# the default limit value (how much documents are returned at once in a
# listing request)
LIMIT_DEFAULT = 30


class DocumentRest(object):

    def __init__(self, request):
        self.request = request

    def _collection_get(self, clazz, schema, adapt_schema=None):
        return self._paginate(clazz, schema, adapt_schema)

    def _paginate(self, clazz, schema, adapt_schema):
        if 'after' in self.request.validated:
            return self._paginate_after(clazz, schema, adapt_schema)
        else:
            return self._paginate_offset(clazz, schema, adapt_schema)

    def _paginate_after(self, clazz, schema, adapt_schema):
        """
        Returns all documents for which `document_id` is smaller than the
        given id in `after`.
        """
        after = self.request.validated['after']
        limit = self.request.validated['limit']
        limit = min(LIMIT_DEFAULT if limit is None else limit, LIMIT_MAX)

        base_query = DBSession.query(clazz)

        documents = base_query. \
            options(joinedload(getattr(clazz, 'locales'))). \
            order_by(clazz.document_id.desc()). \
            filter(clazz.document_id < after). \
            limit(limit). \
            all()
        set_available_cultures(documents)

        return {
            'documents': [
                to_json_dict(
                    doc,
                    schema if not adapt_schema else adapt_schema(schema, doc)
                ) for doc in documents
            ],
            'total': -1
        }

    def _paginate_offset(self, clazz, schema, adapt_schema):
        """Return a batch of documents with the given `offset` and `limit`.
        """
        validated = self.request.validated
        offset = validated['offset'] if 'offset' in validated else 0
        limit = min(
            validated['limit'] if 'limit' in validated else LIMIT_DEFAULT,
            LIMIT_MAX)

        base_query = DBSession.query(clazz)

        documents = base_query. \
            options(joinedload(getattr(clazz, 'locales'))). \
            order_by(clazz.document_id.desc()). \
            slice(offset, offset + limit). \
            all()
        set_available_cultures(documents)

        total = base_query.count()

        return {
            'documents': [
                to_json_dict(
                    doc,
                    schema if not adapt_schema else adapt_schema(schema, doc)
                ) for doc in documents
            ],
            'total': total
        }

    def _get(self, clazz, schema, adapt_schema=None):
        id = self.request.validated['id']
        lang = self.request.GET.get('l')
        return self._get_in_lang(id, lang, clazz, schema, adapt_schema)

    def _get_in_lang(self, id, lang, clazz, schema, adapt_schema=None):
        document = self._get_document(clazz, id, lang)
        set_available_cultures([document])

        if adapt_schema:
            schema = adapt_schema(schema, document)

        return to_json_dict(document, schema)

    def _collection_post(self, clazz, schema):
        document = schema.objectify(self.request.validated)
        document.document_id = None

        DBSession.add(document)
        DBSession.flush()

        user_id = self.request.authenticated_userid
        self._create_new_version(document, user_id)

        sync_search_index(document)

        return to_json_dict(document, schema)

    def _put(self, clazz, schema):
        user_id = self.request.authenticated_userid
        id = self.request.validated['id']
        document_in = \
            schema.objectify(self.request.validated['document'])
        self._check_document_id(id, document_in.document_id)

        # get the current version of the document
        document = self._get_document(clazz, id)
        self._check_versions(document, document_in)

        # remember the current version numbers of the document
        old_versions = document.get_versions()

        # find out whether the update of the geometry should be skipped.
        skip_geometry_update = document_in.geometry is None

        # update the document with the input document
        document.update(document_in)

        try:
            DBSession.flush()
        except StaleDataError:
            raise HTTPConflict('concurrent modification')

        # when flushing the session, SQLAlchemy automatically updates the
        # version numbers in case attributes have changed. by comparing with
        # the old version numbers, we can check if only figures or only locales
        # have changed.
        (update_type, changed_langs) = document.get_update_type(old_versions)

        if update_type:
            # A new version need to be created and persisted
            self._update_version(
                document, user_id, self.request.validated['message'],
                update_type,  changed_langs)

            # And the search updated
            sync_search_index(document)

        json_dict = to_json_dict(document, schema)

        if skip_geometry_update:
            # Optimization: the geometry is not sent back if the client
            # requested to skip the geometry update. Geometries may be very
            # huge; this optimization should speed the data transfer.
            json_dict['geometry'] = None

        return json_dict

    def _get_document(self, clazz, id, culture=None):
        """Get a document with either a single locale (if `culture is given)
        or with all locales.
        If no document exists for the given id, a `HTTPNotFound` exception is
        raised.
        """
        # TODO eager load geometry?
        if not culture:
            document = DBSession. \
                query(clazz). \
                filter(getattr(clazz, 'document_id') == id). \
                options(joinedload(getattr(clazz, 'locales'))). \
                first()
        else:
            document = DBSession. \
                query(clazz). \
                join(getattr(clazz, 'locales')). \
                filter(getattr(clazz, 'document_id') == id). \
                options(contains_eager(getattr(clazz, 'locales'))). \
                filter(DocumentLocale.culture == culture). \
                first()

        if not document:
            raise HTTPNotFound('document not found')

        return document

    def _create_new_version(self, document, user_id):
        assert user_id
        archive = document.to_archive()
        archive_locales = document.get_archive_locales()
        archive_geometry = document.get_archive_geometry()

        meta_data = HistoryMetaData(comment='creation', user_id=user_id)
        versions = []
        for locale in archive_locales:
            version = DocumentVersion(
                document_id=document.document_id,
                culture=locale.culture,
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

        cultures = \
            self._get_cultures_to_update(document, update_types, changed_langs)
        locale_versions = []
        for culture in cultures:
            locale = document.get_locale(culture)
            locale_archive = self._get_locale_archive(locale, changed_langs)

            version = DocumentVersion(
                document_id=document.document_id,
                culture=locale.culture,
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

    def _get_cultures_to_update(self, document, update_types, changed_langs):
        if UpdateType.GEOM not in update_types and \
                UpdateType.FIGURES not in update_types:
            # if the figures or geometry have no been changed, only update the
            # locales that have been changed
            return changed_langs
        else:
            # if the figures or geometry have been changed, update all locales
            return [locale.culture for locale in document.locales]

    def _get_locale_archive(self, locale, changed_langs):
        if locale.culture in changed_langs:
            # create new archive version for this locale
            locale_archive = locale.to_archive()
        else:
            # the locale has not changed, use the old archive version
            locale_archive = DBSession.query(ArchiveDocumentLocale). \
                filter(
                    ArchiveDocumentLocale.version == locale.version,
                    ArchiveDocumentLocale.document_id == locale.document_id,
                    ArchiveDocumentLocale.culture == locale.culture). \
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
            locale = document.get_locale(locale_in.culture)
            if locale:
                if locale.version != locale_in.version:
                    raise HTTPConflict(
                        'version of locale \'%s\' has changed'
                        % locale.culture)
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
            .filter(DocumentVersion.culture == lang) \
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
        .filter(DocumentVersion.culture == lang) \
        .order_by(DocumentVersion.id) \
        .limit(1) \
        .subquery()

    previous_version = DBSession \
        .query(
            DocumentVersion.id.label('id'),
            literal_column('-1').label('t')) \
        .filter(DocumentVersion.id < version_id) \
        .filter(DocumentVersion.document_id == document_id) \
        .filter(DocumentVersion.culture == lang) \
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


def validate_document(document, request, fields, type_field, valid_type_values,
                      updating):
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

    check_required_fields(document, fields_req, request, updating)
    check_duplicate_locales(document, request)


def make_validator_create(fields, type_field, valid_type_values):
    """Returns a validator function used for the creation of documents.
    """
    def f(request):
        document = request.validated
        validate_document(
            document, request, fields, type_field, valid_type_values,
            updating=False)
    return f


def make_validator_update(fields, type_field, valid_type_values):
    """Returns a validator function used for updating documents.
    """
    def f(request):
        document = request.validated.get('document')
        if document:
            validate_document(
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
            .filter(DocumentLocale.culture == lang) \
            .first()

        if not title:
            raise HTTPNotFound('no locale document for ' + lang)

        versions = DBSession.query(DocumentVersion) \
            .options(joinedload('history_metadata').joinedload('user')) \
            .filter(DocumentVersion.document_id == id) \
            .filter(DocumentVersion.culture == lang) \
            .order_by(DocumentVersion.id) \
            .all()

        return {
            'title': title.title,
            'versions': [self._serialize_version(v) for v in versions]
        }
