from sqlalchemy.sql import text
import transaction
import zope

from c2corg_api.scripts.migration.documents.versions import tables_union
from c2corg_api.models.association import Association, AssociationLog
from c2corg_api.scripts.migration.batch import SimpleBatch
from c2corg_api.scripts.migration.migrate_base import MigrateBase

# TODO currently only importing associations for waypoints and routes
associations_query_count =\
    'select count(*) from (' \
    '  select a.main_id, a.linked_id from app_documents_associations a ' \
    '  inner join (' + tables_union + \
    '  ) u on u.id = a.main_id ' \
    '  inner join (' + tables_union + \
    '  ) v on v.id = a.linked_id ' \
    '  group by a.main_id, a.linked_id) t;'

associations_query = \
    'select main_id, linked_id from app_documents_associations a ' \
    'inner join (' + tables_union + \
    ') u on u.id = a.main_id ' \
    'inner join (' + tables_union + \
    ') v on v.id = a.linked_id ' \
    'group by a.main_id, a.linked_id;'

association_log_query_count =\
    'select count(*) from (' \
    '  select associations_log_id from app_associations_log a ' \
    '  inner join (' + tables_union + \
    '  ) u on u.id = a.main_id ' \
    '  inner join (' + tables_union + \
    '  ) v on v.id = a.linked_id ' \
    '  group by associations_log_id) t;'

association_log_query = \
    'select ' \
    '  associations_log_id, main_id, linked_id, user_id, is_creation, ' \
    '  written_at from app_associations_log a ' \
    'inner join (' + tables_union + \
    ') u on u.id = a.main_id ' \
    'inner join (' + tables_union + \
    ') v on v.id = a.linked_id ' \
    'group by associations_log_id;'


class MigrateAssociations(MigrateBase):
    """Migrate associations and association log.
    """

    def migrate(self):
        self._migrate(
            'associations',
            associations_query_count, associations_query, Association,
            self.get_association)
        self._migrate(
            'associations_log',
            association_log_query_count, association_log_query, AssociationLog,
            self.get_log)

    def get_association(self, row):
        return dict(
            parent_document_id=row.main_id,
            child_document_id=row.linked_id
        )

    def get_log(self, row):
        return dict(
            parent_document_id=row.main_id,
            child_document_id=row.linked_id,
            user_id=row.user_id,
            is_creation=row.is_creation,
            written_at=row.written_at
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
