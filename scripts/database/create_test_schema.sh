#!/bin/sh

set -x

DBNAME="c2corg_tests"

if [ "$( psql -tAc "SELECT 1 FROM pg_database WHERE datname='${DBNAME}'" )" = '1' ]
then
    echo "Test database exists: ${DBNAME}"
else
    echo "Create test database: ${DBNAME}"

    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<EOF
create database ${DBNAME} owner "postgres";
\c ${DBNAME}
create extension postgis;
create schema guidebook authorization "postgres";
create schema users authorization "postgres";
create schema sympa authorization "postgres";
create schema alembic authorization "postgres";
\q
EOF
fi
