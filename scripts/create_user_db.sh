#!/bin/sh
sudo -u postgres psql <<EOF
create database c2corg_$USER owner "www-data";
\c c2corg_$USER
create extension postgis;
create schema guidebook authorization "www-data";
create schema users authorization "www-data";
create schema sympa authorization "www-data";
create schema alembic authorization "www-data";
\q
EOF
# to also set up the database, uncomment the following line
# .build/venv/bin/initialize_c2corg_api_db development.ini
