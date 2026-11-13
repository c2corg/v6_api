# Database migration

## Generation of migration scripts

Migration scripts are created each time modifications are made on the database model or data.

For example if you want to add a new field to a table, add the column in the SQLAlchemy
model.

Create the migration script with:

```bash
alembic revision -m 'Add column x'   # in the venv (or: uv run alembic ...), from the root of the repository
```

A new migration script is created in `alembic_migration/versions/`. Add the required database operations to
the script (see [Operation Reference](http://alembic.zzzcomputing.com/en/latest/ops.html)).

To add the new column to the database, run the migration (see below) and make sure the database is updated correctly.

For *replacable objects* like functions or views, the method described in
[documentation](http://alembic.zzzcomputing.com/en/latest/cookbook.html#replaceable-objects)
is used.

## Run a migration

A migration should be run each time the application code is updated or if you have just created a migration script.

```bash
alembic upgrade head   # in the venv (or: uv run alembic upgrade head; make init-database does it too)
```
