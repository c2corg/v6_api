from c2corg_api.models.document_history import HistoryMetaData, DocumentVersion
from c2corg_api.models.document import (
    UpdateType, ArchiveDocumentLocale, ArchiveDocument)
from c2corg_api.models import DBSession


class DocumentRest(object):

    def __init__(self, request):
        self.request = request

    def _create_new_version(self, document):
        archive = document.to_archive()
        archive_locales = document.get_archive_locales()

        meta_data = HistoryMetaData(comment='creation')
        versions = []
        for locale in archive_locales:
            version = DocumentVersion(
                document_id=document.document_id,
                culture=locale.culture,
                version=1,
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
                version=999,
                document_archive=archive,
                document_locales_archive=locale_archive,
                history_metadata=meta_data
            )
            locale_versions.append(version)

        DBSession.add(archive)
#         DBSession.add_all(archive_locales)
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
                filter(ArchiveDocument.version == document.version). \
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
                filter(ArchiveDocumentLocale.version == locale.version). \
                one()
        return locale_archive
