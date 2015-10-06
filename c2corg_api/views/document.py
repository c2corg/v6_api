from sqlalchemy.orm import joinedload, contains_eager
from sqlalchemy.orm.exc import StaleDataError
from pyramid.httpexceptions import HTTPNotFound, HTTPConflict, HTTPBadRequest

from c2corg_api.models.document_history import HistoryMetaData, DocumentVersion
from c2corg_api.models.document import (
    UpdateType, DocumentLocale, ArchiveDocumentLocale, ArchiveDocument,
    ArchiveDocumentGeometry, set_available_cultures)
from c2corg_api.models import DBSession
from c2corg_api.views import to_json_dict
from c2corg_api.views.validation import check_required_fields, \
    check_duplicate_locales


class DocumentRest(object):

    def __init__(self, request):
        self.request = request

    def _paginate_offset(self, clazz, schema, adapt_schema):
        validated = self.request.validated
        offset = validated['offset'] if 'offset' in validated else 0
        limit = validated['limit'] if 'limit' in validated else 30
        total = validated['total'] if 'total' in validated else None

        base_query = DBSession. \
            query(clazz)

        documents = base_query. \
            options(joinedload(getattr(clazz, 'locales'))). \
            order_by(clazz.document_id). \
            slice(offset, offset + limit). \
            all()
        set_available_cultures(documents)

        total = base_query.count() if total is None else total

        return {
            'documents': [
                to_json_dict(
                    doc,
                    schema if not adapt_schema else adapt_schema(schema, doc)
                ) for doc in documents
            ],
            'total': total
        }

    def _paginate_after(self, clazz, schema, adapt_schema):
        after = self.request.validated['after']
        limit = self.request.validated['limit']
        after_id = int(after)
        limit = 30 if limit is None else int(limit)

        base_query = DBSession. \
            query(clazz)

        documents = base_query. \
            options(joinedload(getattr(clazz, 'locales'))). \
            order_by(clazz.document_id). \
            filter(clazz.document_id > after_id). \
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

    def _paginate(self, clazz, schema, adapt_schema):
        if 'after' in self.request.validated:
            return self._paginate_after(clazz, schema, adapt_schema)
        else:
            return self._paginate_offset(clazz, schema, adapt_schema)

    def _collection_get(self, clazz, schema, adapt_schema=None):
        return self._paginate(clazz, schema, adapt_schema)

    def _get(self, clazz, schema, adapt_schema=None):
        id = self.request.validated['id']
        culture = self.request.GET.get('l')
        document = self._get_document(clazz, id, culture)
        set_available_cultures([document])

        if adapt_schema:
            schema = adapt_schema(schema, document)

        return to_json_dict(document, schema)

    def _collection_post(self, clazz, schema):
        document = schema.objectify(self.request.validated)
        document.document_id = None

        DBSession.add(document)
        DBSession.flush()

        self._create_new_version(document)

        return to_json_dict(document, schema)

    def _put(self, clazz, schema):
        id = self.request.validated['id']
        document_in = \
            schema.objectify(self.request.validated['document'])
        self._check_document_id(id, document_in.document_id)

        # get the current version of the document
        document = self._get_document(clazz, id)
        self._check_versions(document, document_in)

        # remember the current version numbers of the document
        old_versions = document.get_versions()

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
        (update_type, changed_langs) = \
            self._check_update_type(document, old_versions)
        self._update_version(
            document, self.request.validated['message'], update_type,
            changed_langs)

        return to_json_dict(document, schema)

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

    def _create_new_version(self, document):
        archive = document.to_archive()
        archive_locales = document.get_archive_locales()
        archive_geometry = document.get_archive_geometry()

        meta_data = HistoryMetaData(comment='creation')
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

    def _update_version(self, document, comment, update_types, changed_langs):
        assert update_types

        meta_data = HistoryMetaData(comment=comment)
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

    def _check_update_type(self, document, old_versions):
        """Get the update types (figures, locales, geometry have changed?).
        """
        (update_types, changed_langs) = document.get_update_type(old_versions)
        if not update_types:
            # nothing has changed, so no need to create a new version
            raise HTTPBadRequest(
                'trying do update the document with the same content')
        return (update_types, changed_langs)


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
