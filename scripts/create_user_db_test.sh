#!/bin/sh

psql <<EOF
create database c2corg_${USER}_tests owner "www-data";
\c c2corg_${USER}_tests
create extension postgis;
create schema guidebook authorization "www-data";
\q
EOF
