from c2corg_api.models.document_history import HistoryMetaData, DocumentVersion
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

    def _update_version(self, document, comment):
        archive = document.to_archive()
        archive_locales = document.get_archive_locales()

        meta_data = HistoryMetaData(comment=comment)
        versions = []
        for locale in archive_locales:
            version = DocumentVersion(
                document_id=document.document_id,
                culture=locale.culture,
                version=999,
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
