from sqlalchemy.ext import compiler
from sqlalchemy.sql.ddl import DDLElement
from sqlalchemy.sql.schema import Table, Column, MetaData

# Support for views in SQLAlchemy
# See: https://bitbucket.org/zzzeek/sqlalchemy/wiki/UsageRecipes/Views
# and: https://github.com/jeffwidman/sqlalchemy-postgresql-materialized-views


class CreateView(DDLElement):
    def __init__(self, name, schema, selectable):
        self.name = name
        self.schema = schema
        self.selectable = selectable


@compiler.compiles(CreateView)
def compile_create_view(element, compiler, **kw):
    return "CREATE OR REPLACE VIEW %s.%s AS %s" % (
        element.schema,
        element.name,
        compiler.sql_compiler.process(element.selectable)
    )


class DropView(DDLElement):
    def __init__(self, name, schema):
        self.name = name
        self.schema = schema


@compiler.compiles(DropView)
def compile_drop_view(element, compiler, **kw):
    return "DROP VIEW IF EXISTS %s.%s" % (element.schema, element.name)


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

    CreateView(name, schema, selectable).execute_at('after-create', metadata)
    DropView(name, schema).execute_at('before-drop', metadata)

    return t
