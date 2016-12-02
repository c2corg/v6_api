""" Extension to handle "replacable ojects" like views or functions in
migration scripts.

As described in:
http://alembic.zzzcomputing.com/en/latest/cookbook.html#replaceable-objects
"""

from alembic.operations import Operations, MigrateOperation
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM


class ReplaceableObject(object):
    def __init__(self, name, sql):
        self.name = name
        self.sql = sql


class ReversibleOp(MigrateOperation):
    def __init__(self, target):
        self.target = target

    @classmethod
    def invoke_for_target(cls, operations, target):
        op = cls(target)
        return operations.invoke(op)

    def reverse(self):
        raise NotImplementedError()

    @classmethod
    def _get_object_from_version(cls, operations, ident):
        version, objname = ident.split(".")

        module = operations.get_context().script.get_revision(version).module
        obj = getattr(module, objname)
        return obj

    @classmethod
    def replace(cls, operations, target, replaces=None, replace_with=None):

        if replaces:
            old_obj = cls._get_object_from_version(operations, replaces)
            drop_old = cls(old_obj).reverse()
            create_new = cls(target)
        elif replace_with:
            old_obj = cls._get_object_from_version(operations, replace_with)
            drop_old = cls(target).reverse()
            create_new = cls(old_obj)
        else:
            raise TypeError("replaces or replace_with is required")

        operations.invoke(drop_old)
        operations.invoke(create_new)


@Operations.register_operation("create_view", "invoke_for_target")
@Operations.register_operation("replace_view", "replace")
class CreateViewOp(ReversibleOp):
    def reverse(self):
        return DropViewOp(self.target)


@Operations.register_operation("drop_view", "invoke_for_target")
class DropViewOp(ReversibleOp):
    def reverse(self):
        return CreateViewOp(self.view)


@Operations.register_operation("create_function", "invoke_for_target")
@Operations.register_operation("replace_function", "replace")
class CreateFunctionOp(ReversibleOp):
    def reverse(self):
        return DropFunctionOp(self.target)


@Operations.register_operation("drop_function", "invoke_for_target")
class DropFunctionOp(ReversibleOp):
    def reverse(self):
        return CreateFunctionOp(self.target)


@Operations.implementation_for(CreateViewOp)
def create_view(operations, operation):
    operations.execute("CREATE VIEW %s AS %s" % (
        operation.target.name,
        operation.target.sql
    ))


@Operations.implementation_for(DropViewOp)
def drop_view(operations, operation):
    operations.execute("DROP VIEW %s" % operation.target.name)


@Operations.implementation_for(CreateFunctionOp)
def create_function(operations, operation):
    operations.execute(
        "CREATE FUNCTION %s %s" % (
            operation.target.name, operation.target.sql
        )
    )


@Operations.implementation_for(DropFunctionOp)
def drop_function(operations, operation):
    operations.execute("DROP FUNCTION %s" % operation.target.name)


def drop_enum(enum_name, schema=None):
    ENUM(name=enum_name, schema=schema).drop(op.get_bind(), checkfirst=False)
