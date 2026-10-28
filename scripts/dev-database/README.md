# Lightweight anonymized dev database

A small (~110 MB dump, ~320 MB once restored), anonymized and consistent extract of the production
database, for development. It keeps the edge cases (see below) and the public transport data
(`stopareas`), so nothing has to be requested from Navitia.

## Using it

The dump is restored by an image on first start (PostgreSQL 18 + PostGIS):

```sh
cp c2corg-dev-pg96.dump scripts/dev-database/c2corg-dev.dump   # or pass --build-arg DUMP=...
docker build -t c2corg-dev-db scripts/dev-database
docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=test c2corg-dev-db
```

Database `c2corg`, user `www-data` (password `www-data`) or `postgres`. It is already at the latest
alembic revision of the code at the time it was built.

Then create and fill the Elasticsearch index, **in this order** (without the first command,
Elasticsearch creates the index on its own without the search sub-fields, and the search silently
returns nothing):

```sh
initialize_c2corg_api_es development.ini    # creates the index and its mappings
fill_es_index development.ini               # ~3 minutes, 65,000 documents, 30 MB
```

Everything (PostgreSQL, Elasticsearch, Redis, the API) fits in about 1.5 GB of memory
(`ES_HEAP_SIZE=512m` is enough for Elasticsearch).

Accounts (password `c2c` for all): `moderator`, `user`, `blocked`, `unvalidated`. Logging in works
without a forum; the API only logs `Could not request nonce` when it cannot reach Discourse.

Public transport: the stop areas come from the dump and are served by `/waypoints/{id}/stopareas`.

Tracks: there are no GPX files. The tracks of routes and outings (about a quarter of them have one) are
geometries with elevation, and they are simplified (tolerance of 10 m, see `20-shrink.sql`) to keep the
dump small. Synchronized activities (Strava, Garmin...) are removed.

## What is kept

| Kept | Why |
|---|---|
| All areas, articles, books, maps, coverages, xreports | few of them, referenced everywhere |
| All waypoints and routes of the zones in `01-setup.sql`, their recent outings (+ a sample of older ones) | realistic content, several langs and countries |
| A corpus of edge cases outside of the zones (`10-select.sql`, rule `edge:*`) | every quality level, protected / redirected documents, longest texts, many langs, no geometry, odd titles... |
| What these documents need (closure): main waypoints, parents, redirect targets, images (max 6 per document), authors | referential integrity |
| Last version of each document; whole history for the edge cases and a sample | the archives tables are huge |
| Stop areas of the kept waypoints | public transport |

The zones and the sampling parameters are at the top of `01-setup.sql`. The reason why each document
is kept is stored in `devdb.keep_doc.reason` during the build.

Personal data is removed by `../anonymize-database/anonymize-data.sql`, then `60-verify.sql` fails the
build if anything is left (emails, passwords, tokens, free texts, profiles...). Its blocking
checks must be extended whenever a table with personal data is added.

## Building it

From a production dump (custom format, as made by the nightly backup: extract
`c2corg.YYYY-MM-DD.dump` from the tar). It runs in a throwaway container, nothing is installed on the host:

```sh
scripts/dev-database/run-in-docker.sh 96 /path/to/c2corg.2026-07-19.dump ./out   # PostgreSQL 9.6
scripts/dev-database/run-in-docker.sh 18 /path/to/c2corg.2026-07-19.dump ./out   # PostgreSQL 18
```

Needs about 10 GB of disk and 4 GB of memory (`MEM=` to change it), and takes around an hour: most of
it is restoring the full dump. The same SQL runs on both versions.

**Prefer the `96` build as long as older PostgreSQL versions must be supported**: its dump can be restored by 9.6 *and* by
18, whereas a dump made by a PostgreSQL 18 server can only be restored by 18.

The production dump contains personal data and must not leave the machine that builds the extract,
nor be committed (`*.dump` is ignored). Only the resulting dump is meant to be shared, after the
checks passed.

## Publishing

```sh
scripts/dev-database/publish.sh c2corg-dev-pg96.dump 2026-07-19
```

It builds the image, restores it in a throwaway container and runs `60-verify.sql` (nothing is pushed if
personal data is left), then asks for a confirmation before pushing the tag and `latest` to
`ghcr.io/c2corg/c2corg-dev-db` (`IMAGE=` to change it, `DRY_RUN=1` to stop before the push). A package
created by a push is private; making it public is done in its settings on GitHub.

## Licence and attribution

The content comes from camptocamp.org and remains subject to the licence stated in the terms of use of
the site (`LICENSE` sets the SPDX identifier put in the image labels: check it before publishing).
The names of the users and the authors of the images are replaced by pseudonyms, but the identifiers of
the documents are kept: every document can be traced back to its page on the site, where its history
and its authors are listed. Image files are not part of the dump, only their rows.
