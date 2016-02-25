from sqlalchemy.sql import text
from c2corg_api.scripts.migration.migrate_base import MigrateBase


class UpdateSequences(MigrateBase):
    sequences = [
        ('guidebook', 'documents_archives', 'id', 'documents_archives_id_seq'),
        ('guidebook', 'documents', 'document_id', 'documents_document_id_seq'),
        ('guidebook', 'documents_geometries_archives', 'id',
            'documents_geometries_archives_id_seq'),
        ('guidebook', 'documents_locales_archives', 'id',
            'documents_locales_archives_id_seq'),
        ('guidebook', 'documents_locales', 'id', 'documents_locales_id_seq'),
        ('guidebook', 'documents_versions', 'id', 'documents_versions_id_seq'),
        ('guidebook', 'history_metadata', 'id', 'history_metadata_id_seq'),
        ('guidebook', 'association_log', 'id', 'association_log_id_seq'),
    ]

    def migrate(self):
        self.start('sequences')
        stmt = "select setval('{0}.{1}', (select max({2}) from {0}.{3}));"
        for schema, table, field, sequence in UpdateSequences.sequences:
            self.session_target.execute(text(
                stmt.format(schema, sequence, field, table)))
        self.stop()
