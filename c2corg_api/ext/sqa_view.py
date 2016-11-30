from sqlalchemy.sql.schema import Table, Column, MetaData

# Support for views in SQLAlchemy
# See: https://bitbucket.org/zzzeek/sqlalchemy/wiki/UsageRecipes/Views
# and: https://github.com/jeffwidman/sqlalchemy-postgresql-materialized-views
#
# Note that the views have to be created explicitly in a migration script.


def view(name, schema, metadata, selectable):
    """
    Create a view for the given select. A table is returned which can be
    used to query the view.
    """
    # a temporary MetaData object is used to avoid that this table is actually
    # created
    t = Table(name, MetaData(), schema=schema)

    for c in selectable.c:
        t.append_column(Column(c.name, c.type, primary_key=c.primary_key))

    return t
