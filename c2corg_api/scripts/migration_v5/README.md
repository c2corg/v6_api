# Database migration script

This package contains a script to migrate the data from version 5 to the new
database schema.

## Configuration

The configuration is made in `migration.ini.in`. After having made changes,
make sure to re-generate the file `migration.ini` with:

    make -f config/{user} load-env

## Prepare the v5 source database

Usernames normalization must be performed (once for all) on the source database
prior to migrating.

    sudo -u postgres psql c2corg -c 'create extension unaccent; create extension intarray; create extension intagg;'
    sudo -u postgres psql c2corg < c2corg_api/scripts/migration/create_unique_normalized_usernames.sql

## Run migration

To start the migration, run:

    .build/venv/bin/python c2corg_api/scripts/migration/migrate.py

## Initialize ElasticSearch

After the database migration, ElasticSearch has to be fed with the documents.

Make sure that the index exists:

    .build/venv/bin/initialize_c2corg_api_es development.ini

Then start the import:

    .build/venv/bin/fill_es_index development.ini

For production instances rather use

    .build/venv/bin/initialize_c2corg_api_es production.ini
    .build/venv/bin/fill_es_index production.ini

## Import topic_ids from discourse

After the discourse migration, we need to update the `documents_topics`
table. This is done using the shell script `scripts/update_topic_ids.sh`.

Before running the script we need access to the discourse database. For now
this could be done by binding host port 5433 to discourse container port 5432,
but this is subject to change when running `v6_api` with docker.

In file `/var/discourse/containers/c2corgv6.yml` expose port 5432 to host
port 5433:

    ## which TCP/IP ports should this container expose?
    expose:
      - "5433:5432"  # fwd host port 5433 to container port 5432 (postgresql)

Restart the container (in `/var/discourse/` folder):

    ./launcher restart c2corgv6

Now you can run the script (in `v6_api` folder) after verification that it
exactly fits your needs:

    scripts/update_topic_ids.sh

And finally, you should remove the temporary port binding from the config and
restart the discourse container.
