create user "www-data" with password 'www-data';
create database c2corg_tests owner "www-data";
\c c2corg_tests
create extension postgis;
create schema topoguide authorization "www-data";
\q
