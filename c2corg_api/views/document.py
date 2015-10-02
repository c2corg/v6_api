from sqlalchemy.orm import joinedload, contains_eager
from sqlalchemy.orm.exc import StaleDataError
from pyramid.httpexceptions import HTTPNotFound, HTTPConflict, HTTPBadRequest

from c2corg_api.models.document_history import HistoryMetaData, DocumentVersion
from c2corg_api.models.document import (
    UpdateType, DocumentLocale, ArchiveDocumentLocale, ArchiveDocument)
from c2corg_api.models import DBSession
from c2corg_api.views import to_json_dict


class DocumentRest(object):

    def __init__(self, request):
        self.request = request

    def _collection_get(self, clazz, schema):
        documents = DBSession. \
            query(clazz). \
            options(joinedload(getattr(clazz, 'locales'))). \
            limit(30)

        return [to_json_dict(doc, schema) for doc in documents]

    def _get(self, clazz, schema):
        id = self.request.validated['id']
        culture = self.request.GET.get('l')
        document = self._get_document(clazz, id, culture)

        return to_json_dict(document, schema)

    def _collection_post(self, clazz, schema):
        document = schema.objectify(self.request.validated)

        # TODO additional validation: at least one culture, only one instance
        # for each culture

        DBSession.add(document)
        DBSession.flush()

        self._create_new_version(document)

        return to_json_dict(document, schema)

    def _put(self, clazz, schema):
        id = self.request.validated['id']
        document_in = \
            schema.objectify(self.request.validated['document'])
        self._check_document_id(id, document_in.document_id)

        document = self._get_document(clazz, id)
        self._check_versions(document, document_in)
        old_versions = document.get_versions()
        document.update(document_in)

        try:
            DBSession.flush()
        except StaleDataError:
            raise HTTPConflict('concurrent modification')

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

        meta_data = HistoryMetaData(comment='creation')
        versions = []
        for locale in archive_locales:
            version = DocumentVersion(
                document_id=document.document_id,
                culture=locale.culture,
                document_archive=archive,
                document_locales_archive=locale,
                history_metadata=meta_data
            )
            versions.append(version)

        DBSession.add(archive)
        DBSession.add_all(archive_locales)
        DBSession.add(meta_data)
        DBSession.add_all(versions)
        DBSession.flush()

    def _update_version(self, document, comment, update_type, changed_langs):
        assert update_type != UpdateType.NONE

        meta_data = HistoryMetaData(comment=comment)
        archive = self._get_document_archive(document, update_type)

        cultures = \
            self._get_cultures_to_update(document, update_type, changed_langs)
        locale_versions = []
        for culture in cultures:
            locale = document.get_locale(culture)
            locale_archive = self._get_locale_archive(locale, changed_langs)

            version = DocumentVersion(
                document_id=document.document_id,
                culture=locale.culture,
                document_archive=archive,
                document_locales_archive=locale_archive,
                history_metadata=meta_data
            )
            locale_versions.append(version)

        DBSession.add(archive)
        DBSession.add(meta_data)
        DBSession.add_all(locale_versions)
        DBSession.flush()

    def _get_document_archive(self, document, update_type):
        if (update_type == UpdateType.FIGURES_ONLY or
                update_type == UpdateType.ALL):
            # the document has changed, create a new archive version
            archive = document.to_archive()
        else:
            # the document has not changed, load the previous archive version
            archive = DBSession.query(ArchiveDocument). \
                filter(
                    ArchiveDocument.version_hash == document.version_hash). \
                one()
        return archive

    def _get_cultures_to_update(self, document, update_type, changed_langs):
        if update_type == UpdateType.LANG_ONLY:
            # if the figures have no been changed, only update the locales that
            # have been changed
            return changed_langs
        else:
            # if the figures have been changed, update all locales
            return [locale.culture for locale in document.locales]

    def _get_locale_archive(self, locale, changed_langs):
        if locale.culture in changed_langs:
            # create new archive version for this locale
            locale_archive = locale.to_archive()
        else:
            # the locale has not changed, use the old archive version
            locale_archive = DBSession.query(ArchiveDocumentLocale). \
                filter(
                    ArchiveDocumentLocale.version_hash ==
                    locale.version_hash). \
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
        """Check that the passed-in document and all passed-in locales have
        the same version as the current document and locales in the database.
        If not (that is the document has changed), a `HTTPConflict` exception
        is raised.
        """
        if document.version_hash != document_in.version_hash:
            raise HTTPConflict('version of document has changed')
        for locale_in in document_in.locales:
            locale = document.get_locale(locale_in.culture)
            if locale:
                if locale.version_hash != locale_in.version_hash:
                    raise HTTPConflict(
                        'version of locale \'%s\' has changed'
                        % locale.culture)

    def _check_update_type(self, document, old_versions):
        """Get the update type (only figures have changed, only locales have
        changed, both have changed or nothing).
        """
        (update_type, changed_langs) = document.get_update_type(old_versions)
        if update_type == UpdateType.NONE:
            # nothing has changed, so no need to create a new version
            raise HTTPBadRequest(
                'trying do update the document with the same content')
        return (update_type, changed_langs)
