from c2corg_api.models.document import ArchiveDocument, ArchiveDocumentLocale
from c2corg_api.scripts.migration.documents.user_profiles import \
    MigrateUserProfiles
from sqlalchemy.sql import text
import transaction
import zope
from c2corg_api.models.document_history import HistoryMetaData, DocumentVersion

from c2corg_api.scripts.migration.batch import SimpleBatch
from c2corg_api.scripts.migration.migrate_base import MigrateBase

# TODO only importing the versions of the tables listed below
tables = [
    'articles', 'huts', 'parkings', 'products', 'sites', 'summits', 'routes',
    'maps', 'areas', 'outings', 'images'
]
tables_union = ' union '.join(
    ['select id, redirects_to from ' + t for t in tables]) + \
    ' union select up.id, up.redirects_to from users up ' \
    ' join app_users_private_data u on up.id = u.id'

metadata_query_count =\
    'select count(*) ' \
    'from (select h.history_metadata_id from ' \
    '   app_history_metadata h ' \
    '      inner join app_documents_versions v ' \
    '        on h.history_metadata_id = v.history_metadata_id ' \
    '      inner join (' + tables_union + \
    '      ) u on u.id = v.document_id and u.redirects_to is null ' \
    '   group by h.history_metadata_id) t;'

metadata_query = \
    'select h.history_metadata_id, h.user_id, h.comment, h.written_at ' \
    'from ' \
    '   app_history_metadata h ' \
    '     inner join app_documents_versions v ' \
    '        on h.history_metadata_id = v.history_metadata_id ' \
    '     inner join (' + tables_union + \
    '     ) u on u.id = v.document_id and u.redirects_to is null ' \
    'group by h.history_metadata_id'

versions_query_count =\
    'select count(*) ' \
    'from (select v.documents_versions_id from ' \
    '   app_documents_versions v ' \
    '   inner join (' + tables_union + \
    '   ) u on u.id = v.document_id and u.redirects_to is null ' \
    '  group by v.documents_versions_id) t;'

versions_query =\
    'select ' \
    '   v.documents_versions_id, v.document_id, v.culture, ' \
    '   v.document_archive_id, v.document_i18n_archive_id, ' \
    '   v.history_metadata_id ' \
    'from app_documents_versions v ' \
    '   inner join (' + tables_union + \
    '   ) u on u.id = v.document_id and u.redirects_to is null ' \
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

        # there are a couple of users that did not have a profile (see
        # MigrateUserProfiles). now also create a version for the created
        # profiles.
        with transaction.manager:
            profileless_users = self.connection_source.execute(
                text(MigrateUserProfiles.query_profileless_users))
            last_metadata_id = self.connection_source.execute(
                text('select max(history_metadata_id) '
                     'from app_history_metadata;')).fetchone()[0]
            last_version_id = self.connection_source.execute(
                text('select max(documents_versions_id) '
                     'from app_documents_versions;')).fetchone()[0]

            for row in profileless_users:
                user_id = row[0]
                last_metadata_id += 1
                last_version_id += 1

                archive = self.session_target.query(ArchiveDocument).filter(
                    ArchiveDocument.document_id == user_id).one()
                locale = self.session_target.query(ArchiveDocumentLocale). \
                    filter(ArchiveDocumentLocale.document_id == user_id).one()

                meta_data = HistoryMetaData(
                    id=last_metadata_id,
                    comment='creation', user_id=user_id)
                version = DocumentVersion(
                    id=last_version_id,
                    document_id=user_id,
                    lang=locale.lang,
                    document_archive=archive,
                    document_locales_archive=locale,
                    history_metadata=meta_data
                )
                self.session_target.add(version)

    def get_meta_data(self, row):
        if row.history_metadata_id == 75191:
            # the user_id (8040) is wrong for this entry, use the user_id of
            # the user who created the outing
            user_id = 206753
        else:
            user_id = row.user_id

        return dict(
            id=row.history_metadata_id,
            user_id=user_id,
            comment=row.comment,
            written_at=row.written_at
        )

    def get_version(self, row):
        return dict(
            id=row.documents_versions_id,
            document_id=row.document_id,
            lang=row.culture,
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
