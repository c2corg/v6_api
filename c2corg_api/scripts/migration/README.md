Database migration script
=========================

This package contains a script to migrate the data from version 5 to the new
database schema.

Configuration
-------------

The configuration is made in `migration.ini.in`. After having made changes,
make sure to re-generate the file `migration.ini` with:

    make -f config/{user} template

Prepare the v5 source database
------------------------------

Usernames normalization must be performed (once for all) on the source database
prior to migrating.

    sudo -u postgres psql c2corg -c 'create extension unaccent; create extension intarray; create extension intagg;'
    sudo -u postgres psql c2corg < c2corg_api/scripts/migration/create_unique_normalized_usernames.sql

Run migration
-------------

To start the migration, run:

    .build/venv/bin/python c2corg_api/scripts/migration/migrate.py

Initialize ElasticSearch
-------------------------

After the database migration, ElasticSearch has to be fed with the documents.

Make sure that the index exists:

    .build/venv/bin/initialize_c2corg_api_es development.ini

Then start the import:

    .build/venv/bin/fill_es_index development.ini

For productive instances rather use

    .build/venv/bin/initialize_c2corg_api_es production.ini
    .build/venv/bin/fill_es_index production.ini
