#!/bin/sh

DBNAME="c2corg_${USER}_tests"
[ -z "$USER" ] && DBNAME="c2corg_tests"

if [ "$( psql -tAc "SELECT 1 FROM pg_database WHERE datname='${DBNAME}'" )" = '1' ]
then
    echo "Test database exists"
else
    echo "Create test database"

    psql <<EOF
create database ${DBNAME} owner "www-data";
\c ${DBNAME}
create extension postgis;
create schema guidebook authorization "www-data";
create schema users authorization "www-data";
create schema sympa authorization "www-data";
create schema alembic authorization "www-data";
\q
EOF
fi
