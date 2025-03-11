#!/bin/sh
DBNAME="c2corg"

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
# to also set up the database, uncomment the following line
# .build/venv/bin/initialize_c2corg_api_db development.ini
