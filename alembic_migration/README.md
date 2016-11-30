# Database migration

## Generation of migration scripts

Migration scripts are created each time modifications are made on the database model or data.

For example if you want to add a new field to a table, add the column in the SQLAlchemy
model.

Then auto-generate the migration script with:

```
.build/venv/bin/alembic revision --autogenerate -m 'Add column x'
```

A new migration script is created in `alembic_migration/versions/`. Make sure the script looks correct, adjust if necessary.

To add the new column to the database, run the migration (see below) and make sure the database is updated correctly.

Note that not all changes are detected, see [Auto Generating Migrations](http://alembic.zzzcomputing.com/en/latest/autogenerate.html)
for more information.

For *replacable objects* like functions or views, the method described in
[documentation](http://alembic.zzzcomputing.com/en/latest/cookbook.html#replaceable-objects)
is used.

## Run a migration

A migration should be run each time the application code is updated or if you have just created a migration script.

```
.build/venv/bin/alembic upgrade head
```
