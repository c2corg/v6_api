#!/bin/sh

PSQL=psql

DBNAME="c2corg_${USER}_tests"
[ -z "$USER" ] && DBNAME="c2corg_tests"

$PSQL <<EOF
create database ${DBNAME} owner "www-data";
\c ${DBNAME}
create extension postgis;
create schema guidebook authorization "www-data";
create schema users authorization "www-data";
create schema sympa authorization "www-data";
create schema alembic authorization "www-data";
\q
EOF
