#!/bin/bash
# Run once by the postgres image entrypoint, on an empty data directory.
set -euo pipefail

psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres <<'SQL'
create role "www-data" login password 'www-data';
create database c2corg owner "www-data";
SQL
# the schema `public` comes with every database
DUMP=/docker-entrypoint-initdb.d/c2corg-dev.dump
pg_restore -l "$DUMP" | grep -v ' SCHEMA - public ' > /tmp/restore.list
pg_restore -U "$POSTGRES_USER" -d c2corg --no-owner --exit-on-error -L /tmp/restore.list "$DUMP"
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d c2corg <<'SQL'
grant all on all tables in schema guidebook, users, tracking, sympa, alembic to "www-data";
grant all on all sequences in schema guidebook, users, tracking, sympa, alembic to "www-data";
grant usage on schema guidebook, users, tracking, sympa, alembic to "www-data";
SQL
rm /tmp/restore.list
