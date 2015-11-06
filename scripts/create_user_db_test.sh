#!/bin/sh

PSQL=psql
[ "$USER" != "travis" ] && PSQL="sudo -u postgres psql"

$PSQL <<EOF
create database c2corg_${USER}_tests owner "www-data";
\c c2corg_${USER}_tests
create extension postgis;
create schema guidebook authorization "www-data";
create schema users authorization "www-data";
\q
EOF
