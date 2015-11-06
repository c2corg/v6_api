#!/bin/sh

PSQL=psql
[ "$USER" != "travis" ] && PSQL="sudo -u postgres psql"

DBNAME="c2corg_${USER}_tests"
[ -z "$USER" ] && DBNAME="c2corg_tests"

$PSQL <<EOF
create database ${DBNAME} owner "www-data";
\c ${DBNAME}
create extension postgis;
create schema guidebook authorization "www-data";
create schema users authorization "www-data";
\q
EOF
