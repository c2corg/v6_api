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

        # `ANALYZE` does not support bound parameters for identifiers
        # (schema/table names), so the identifiers returned by
        # SQL_ALL_TABLES (not user input: they come from Postgres' own
        # catalog, already filtered to our two known schemas) are quoted
        # with the dialect's identifier preparer instead of being
        # interpolated into the SQL string as raw strings.
        preparer = engine.dialect.identifier_preparer

        all_tables = conn.execute(text(SQL_ALL_TABLES))
        for schema, table in all_tables:
            qualified_name = '{}.{}'.format(
                preparer.quote(schema), preparer.quote(table))
            conn.execute(text('analyze {};'.format(qualified_name)))

        conn.connection.set_isolation_level(old_lvl)
        conn.close()

        self.stop()


SQL_ALL_TABLES = """
SELECT schemaname, relname
FROM pg_stat_all_tables
WHERE schemaname in ('guidebook', 'users');
"""
