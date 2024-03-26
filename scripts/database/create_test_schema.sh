#!/bin/sh

DBNAME="c2corg_tests"

if [ "$( psql -tAc "SELECT 1 FROM pg_database WHERE datname='${DBNAME}'" )" = '1' ]
then
    echo "Test database exists"
else
    echo "Create test database"

    psql <<EOF
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
