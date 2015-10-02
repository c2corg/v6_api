#!/bin/sh
psql <<EOF
create database c2corg_$USER owner "www-data";
\c c2corg_$USER
create extension postgis;
create schema guidebook authorization "www-data";
\q
.build/venv/bin/initialize_c2corg_api_db development.ini
EOF
