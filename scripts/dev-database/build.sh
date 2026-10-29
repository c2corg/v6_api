#!/bin/bash
# Builds the lightweight, anonymized dev database from a production dump.
#
#   build.sh <c2corg.YYYY-MM-DD.dump> <output.dump>
#
# It needs the PostgreSQL client tools (psql, pg_restore, pg_dump) and a PostgreSQL server with
# PostGIS, reachable with the usual PG* variables (PGHOST, PGUSER...). The user must be a superuser.
# The database `c2corg` is (re)created on that server, and is the scratch space of the build.
#
# SKIP_RESTORE=1 reuses the `c2corg` database as it is (an already restored dump), to iterate.
# ANONYMIZE_SQL overrides the anonymization script (default: ../anonymize-database/anonymize-data.sql).

set -euo pipefail

DUMP=${1:?usage: build.sh <production dump> <output dump>}
OUT=${2:?usage: build.sh <production dump> <output dump>}
HERE=$(cd "$(dirname "$0")" && pwd)
ANONYMIZE_SQL=${ANONYMIZE_SQL:-$HERE/../anonymize-database/anonymize-data.sql}
DB=c2corg # the anonymization script connects to this database
SCHEMAS='guidebook|users|tracking|sympa|alembic'
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

sql() { psql -X -q -v ON_ERROR_STOP=1 -d "$DB" "$@"; }
step() { echo "=== $(date +%H:%M:%S) $*"; }

if [ -z "${SKIP_RESTORE:-}" ]; then
  step "restoring the schema and the data of $DUMP (without indexes and foreign keys)"
  psql -X -q -d postgres -c "drop database if exists $DB"
  psql -X -q -d postgres -tc "select 1 from pg_roles where rolname = 'www-data'" | grep -q 1 \
    || psql -X -q -d postgres -c 'create role "www-data" login'
  psql -X -q -d postgres -c "create database $DB owner \"www-data\""

  # The schema `public` comes with every database: it is left out, and any other error stops the build
  pg_restore -l "$DUMP" | grep -v ' SCHEMA - public ' > "$WORK/pre.list"
  pg_restore --section=pre-data --exit-on-error --no-owner --no-acl -L "$WORK/pre.list" -d "$DB" "$DUMP"

  # The data of our schemas only: the PostGIS / tiger tables are already there
  pg_restore -l "$DUMP" | awk -v re="^($SCHEMAS)$" \
    '(($4 == "TABLE" && $5 == "DATA") || ($4 == "SEQUENCE" && $5 == "SET")) && $6 ~ re' > "$WORK/data.list"
  pg_restore --section=data --no-owner --no-acl -L "$WORK/data.list" -j 2 -d "$DB" "$DUMP"
fi

step "selecting what is kept"
sql -f "$HERE/01-setup.sql"
sql -f "$HERE/10-select.sql"

step "shrinking the tables"
sql -f "$HERE/20-shrink.sql"

step "removing personal data"
sql -f "$ANONYMIZE_SQL"
sql -f "$HERE/50-test-accounts.sql"

step "restoring the indexes and the foreign keys (fails if the selection is not consistent)"
pg_restore -l "$DUMP" | grep -E " ($SCHEMAS) " > "$WORK/post.list"
pg_restore --section=post-data --exit-on-error --no-owner --no-acl -L "$WORK/post.list" -d "$DB" "$DUMP"

step "checking the result"
sql -f "$HERE/60-verify.sql"

step "cleaning up"
sql -c 'drop schema devdb cascade'
psql -X -q -d "$DB" -c 'vacuum analyze'

step "dumping into $OUT"
pg_dump --format=custom --no-owner --no-acl -d "$DB" -f "$OUT"
ls -lh "$OUT"
