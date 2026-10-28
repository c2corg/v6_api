#!/bin/bash
# Builds the dev database in a throwaway PostgreSQL container, so that nothing has to be installed
# or loaded on the host. The container and its volume are removed at the end.
#
#   run-in-docker.sh <96|18> <production dump> <output directory>
#
#   96  PostgreSQL 9.6 (legacy). The resulting dump can be restored by 9.6 and by 18.
#   18  PostgreSQL 18. The resulting dump can only be restored by 18 (pg_dump is not backward compatible).
#
# The production dump (custom format, as made by the nightly backup) is only read, never modified.
# Variables: MEM (memory limit of the container, default 4g), PG96_IMAGE, PG18_IMAGE.

set -euo pipefail

VERSION=${1:?usage: run-in-docker.sh <96|18> <production dump> <output directory>}
DUMP=${2:?usage: run-in-docker.sh <96|18> <production dump> <output directory>}
OUTDIR=${3:?usage: run-in-docker.sh <96|18> <production dump> <output directory>}

case "$VERSION" in
  96) IMAGE=${PG96_IMAGE:-c2corg/c2corg_pgsql:9.6.1-postgis2.3} ;;
  18) IMAGE=${PG18_IMAGE:-postgis/postgis:18-3.6} ;;
  *) echo "unknown version: $VERSION (expected 96 or 18)" >&2; exit 1 ;;
esac

# docker needs absolute paths (native ones with Git Bash on Windows)
native() { if command -v cygpath > /dev/null; then cygpath -m "$1"; else echo "$1"; fi; }
abspath() { (cd "$(dirname "$1")" && echo "$PWD/$(basename "$1")"); }
SCRIPTS=$(cd "$(dirname "$0")/.." && pwd) # the `scripts` directory: dev-database and anonymize-database
DUMP=$(abspath "$DUMP")
mkdir -p "$OUTDIR"
OUTDIR=$(cd "$OUTDIR" && pwd)
OUT=c2corg-dev-pg$VERSION.dump

NAME=devdb-build-$VERSION-$$
VOLUME=$NAME-data
export MSYS_NO_PATHCONV=1 # Git Bash on Windows

cleanup() {
  docker rm -f "$NAME" > /dev/null 2>&1 || true
  docker volume rm "$VOLUME" > /dev/null 2>&1 || true
}
trap cleanup EXIT

docker volume create "$VOLUME" > /dev/null
# Settings for a one-off bulk load: no durability needed, the whole container is thrown away.
# PGDATA is explicit because the image layouts differ between 9.6 and 18.
docker run -d --name "$NAME" --memory "${MEM:-4g}" --shm-size 512m \
  -e POSTGRES_PASSWORD=build -e PGDATA=/var/lib/postgresql/data/pgdata \
  -v "$VOLUME":/var/lib/postgresql/data \
  -v "$(native "$SCRIPTS")":/scripts:ro \
  -v "$(native "$(dirname "$DUMP")")":/dump:ro \
  -v "$(native "$OUTDIR")":/out \
  "$IMAGE" postgres \
  -c shared_buffers=512MB -c maintenance_work_mem=512MB -c work_mem=32MB \
  -c fsync=off -c synchronous_commit=off -c full_page_writes=off \
  -c max_wal_size=8GB -c checkpoint_timeout=30min -c autovacuum=off > /dev/null

# On an empty data directory the entrypoint runs a temporary server to initialize, then restarts:
# the final server is the second one to announce itself
for _ in $(seq 1 90); do
  [ "$(docker logs "$NAME" 2>&1 | grep -c 'ready to accept connections')" -ge 2 ] && break
  sleep 2
done
docker exec "$NAME" pg_isready -U postgres

docker exec -e PGUSER=postgres "$NAME" bash /scripts/dev-database/build.sh "/dump/$(basename "$DUMP")" "/out/$OUT"
echo "done: $OUTDIR/$OUT"
