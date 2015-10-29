from sqlalchemy.sql import text
import transaction
import zope
import abc

from c2corg_api.scripts.migration.documents.batch_document import DocumentBatch
from c2corg_api.scripts.migration.migrate_base import MigrateBase


class MigrateDocuments(MigrateBase):

    def __init__(self, connection_source, session_target, batch_size):
        super(MigrateDocuments, self).__init__(
            connection_source, session_target, batch_size)

    @abc.abstractmethod
    def get_model_document(self, locales):
        pass

    @abc.abstractmethod
    def get_model_archive_document(self, locales):
        pass

    @abc.abstractmethod
    def get_model_geometry(self):
        pass

    @abc.abstractmethod
    def get_model_archive_geometry(self):
        pass

    @abc.abstractmethod
    def get_query(self):
        pass

    @abc.abstractmethod
    def get_count_query(self):
        pass

    @abc.abstractmethod
    def get_document(self, document_in, version):
        pass

    @abc.abstractmethod
    def get_document_archive(self, document_in, version):
        pass

    @abc.abstractmethod
    def get_document_geometry(self, document_in, version):
        pass

    @abc.abstractmethod
    def get_document_geometry_archive(self, document_in, version):
        pass

    @abc.abstractmethod
    def get_document_locale(self, document_in, version):
        pass

    @abc.abstractmethod
    def get_document_locale_archive(self, document_in, version):
        pass

    @abc.abstractmethod
    def get_name(self):
        pass

    def migrate(self):
        self._migrate(locales=False)
        self._migrate(locales=True)

    def _migrate(self, locales=False):
        self.start('{0}{1}'.format(
            'locales of ' if locales else '',
            self.get_name()))

        query_count = self.get_count_query_locales() if locales else \
            self.get_count_query()
        total_count = self.connection_source.execute(
            text(query_count)).fetchone()[0]

        print('Total: {0} rows'.format(total_count))

        query = text(self.get_query_locales() if locales else self.get_query())
        batch = DocumentBatch(
            self.session_target, self.batch_size,
            self.get_model_document(locales),
            self.get_model_archive_document(locales),
            self.get_model_geometry(),
            self.get_model_archive_geometry())
        with transaction.manager, batch:
            count = 0
            current_document_id = None
            version = 1
            archives = []
            geometry_archives = []

            for document_in in self.connection_source.execute(query):
                count += 1
                if current_document_id is None:
                    current_document_id = document_in.id
                else:
                    if current_document_id != document_in.id:
                        raise AssertionError(
                            'no latest version for {0}'.format(
                                current_document_id))
                if locales:
                    document_archive = self.get_document_locale_archive(
                        document_in, version)
                else:
                    document_archive = self.get_document_archive(
                        document_in, version)
                    geometry_archive = self.get_document_geometry_archive(
                            document_in, version)
                    geometry_archives.append(geometry_archive)
                archives.append(document_archive)

                if document_in.is_latest_version:
                    version = 1
                    current_document_id = None

                    if locales:
                        document = self.get_document_locale(
                            document_in, version)
                    else:
                        document = self.get_document(
                            document_in, version)
                        geometry = self.get_document_geometry(
                                document_in, version)
                        batch.add_geometry(geometry)
                    batch.add_geometry_archives(geometry_archives)
                    batch.add_archive_documents(archives)
                    batch.add_document(document)
                    archives = []
                    geometry_archives = []
                else:
                    version += 1
                self.progress(count, total_count)

            # the transaction will not be commited automatically when doing
            # a bulk insertion. `mark_changed` forces a commit.
            zope.sqlalchemy.mark_changed(self.session_target)
        self.stop()
