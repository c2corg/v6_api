from sqlalchemy.sql import text

from c2corg_api.scripts.migration.migrate_base import MigrateBase


class AnalyzeAllTables(MigrateBase):
    """Run "analyze" on all tables.
    """

    def migrate(self):
        self.start('analyze')

        # run analyze on the table (must be outside a transaction)
        engine = self.session_target.bind
        conn = engine.connect()
        old_lvl = conn.connection.isolation_level
        conn.connection.set_isolation_level(0)

        all_tables = conn.execute(text(SQL_ALL_TABLES))
        for schema, table in all_tables:
            conn.execute('analyze {}.{};'.format(schema, table))

        conn.connection.set_isolation_level(old_lvl)
        conn.close()

        self.stop()


SQL_ALL_TABLES = """
SELECT schemaname, relname
FROM pg_stat_all_tables
WHERE schemaname in ('guidebook', 'users');
"""
