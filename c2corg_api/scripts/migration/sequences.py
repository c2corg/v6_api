from sqlalchemy.sql import text
from c2corg_api.scripts.migration.migrate_base import MigrateBase


class UpdateSequences(MigrateBase):
    sequences = [
        ('documents_archives', 'id', 'documents_archives_id_seq'),
        ('documents', 'document_id', 'documents_document_id_seq'),
        ('documents_geometries_archives', 'id',
            'documents_geometries_archives_id_seq'),
        ('documents_locales_archives', 'id',
            'documents_locales_archives_id_seq'),
        ('documents_locales', 'id', 'documents_locales_id_seq'),
        ('documents_versions', 'id', 'documents_versions_id_seq'),
        ('history_metadata', 'id', 'history_metadata_id_seq')
    ]

    def migrate(self):
        self.start('sequences')
        update_stmt = "select setval('guidebook.{0}', (select max({1}) from " \
                      "guidebook.{2}));"
        for table, field, sequence in UpdateSequences.sequences:
            self.session_target.execute(text(
                update_stmt.format(sequence, field, table)))
        self.stop()
