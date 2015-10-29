from sqlalchemy.sql import text
import transaction
import zope
from c2corg_api.models.document_history import HistoryMetaData, DocumentVersion

from c2corg_api.scripts.migration.batch import SimpleBatch
from c2corg_api.scripts.migration.migrate_base import MigrateBase

# TODO currently limited to the history of summits!
metadata_query_count =\
    'select count(*) ' \
    'from (select h.history_metadata_id from ' \
    '   app_history_metadata h ' \
    '      inner join app_documents_versions v ' \
    '        on h.history_metadata_id = v.history_metadata_id ' \
    '      inner join app_summits_archives a on a.id = v.document_id' \
    '   group by h.history_metadata_id) t;'

metadata_query = \
    'select h.history_metadata_id, h.user_id, h.comment, h.written_at ' \
    'from ' \
    '   app_history_metadata h ' \
    '     inner join app_documents_versions v ' \
    '        on h.history_metadata_id = v.history_metadata_id ' \
    '     inner join app_summits_archives a on a.id = v.document_id ' \
    'group by h.history_metadata_id'

versions_query_count =\
    'select count(*) ' \
    'from (select v.documents_versions_id from ' \
    '   app_documents_versions v inner join app_summits_archives a ' \
    '      on a.id = v.document_id ' \
    '  group by v.documents_versions_id) t;'

versions_query =\
    'select ' \
    '   v.documents_versions_id, v.document_id, v.culture, ' \
    '   v.document_archive_id, v.document_i18n_archive_id, ' \
    '   v.history_metadata_id ' \
    'from app_documents_versions v inner join app_summits_archives a ' \
    '   on a.id = v.document_id ' \
    'group by v.documents_versions_id;'


class MigrateVersions(MigrateBase):

    def migrate(self):
        self._migrate(
            'history_metadata',
            metadata_query_count, metadata_query, HistoryMetaData,
            self.get_meta_data)
        self._migrate(
            'documents_versions',
            versions_query_count, versions_query, DocumentVersion,
            self.get_version)

    def get_meta_data(self, row):
        return dict(
            id=row.history_metadata_id,
            # user_id=user_id,
            comment=row.comment,
            written_at=row.written_at
        )

    def get_version(self, row):
        return dict(
            id=row.documents_versions_id,
            document_id=row.document_id,
            culture=row.culture,
            document_archive_id=row.document_archive_id,
            document_locales_archive_id=row.document_i18n_archive_id,
            document_geometry_archive_id=row.document_archive_id,
            history_metadata_id=row.history_metadata_id
        )

    def _migrate(self, label, query_count, query, model, get_entity):
        self.start(label)

        total_count = self.connection_source.execute(
            text(query_count)).fetchone()[0]

        print('Total: {0} rows'.format(total_count))

        query = text(query)
        batch = SimpleBatch(
            self.session_target, self.batch_size, model)
        with transaction.manager, batch:
            count = 0
            for entity_in in self.connection_source.execute(query):
                count += 1
                batch.add(get_entity(entity_in))
                self.progress(count, total_count)

            # the transaction will not be commited automatically when doing
            # a bulk insertion. `mark_changed` forces a commit.
            zope.sqlalchemy.mark_changed(self.session_target)
        self.stop()
