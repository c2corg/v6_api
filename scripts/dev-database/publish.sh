#!/bin/bash
# Builds the dev database image from a dump and the Elasticsearch image indexed from it, checks them and
# pushes both to the GitHub container registry, with the same tags: they always match.
#
#   publish.sh <dump made by build.sh> <tag>        e.g. publish.sh c2corg-dev-pg96.dump 2026-07-19
#
# 1. builds the database image locally, 2. starts it and runs 60-verify.sql (no personal data left),
# 3. fills an Elasticsearch from that database with the indexing code of this checkout (a few minutes,
#    about 1.5 GB of memory more) and builds the Elasticsearch image from it, 4. checks it,
# 5. asks for confirmation, 6. pushes <tag> and `latest` of both images.
#
# Run it from a checkout of the version of the API the images are meant for: the index is built by its
# code, and the fingerprint of that code is stored in the image (see c2corg_api/scripts/es/fingerprint.py).
#
# Needs `docker login ghcr.io` with a token which can write packages. A package created by a push is
# private: making it public is done in the package settings on GitHub, it cannot be done from here.
#
# Variables: IMAGE (default ghcr.io/c2corg/c2corg-dev-db), ES_IMAGE (default ghcr.io/c2corg/c2corg-dev-es),
# DRY_RUN=1 to stop before the push, PUSH="es" (or "db") to push only one of the two images
# (default "db es").

set -euo pipefail

DUMP=${1:?usage: publish.sh <dump> <tag>}
TAG=${2:?usage: publish.sh <dump> <tag>}
IMAGE=${IMAGE:-ghcr.io/c2corg/c2corg-dev-db}
ES_IMAGE=${ES_IMAGE:-ghcr.io/c2corg/c2corg-dev-es}
PUSH=${PUSH:-db es}
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
export MSYS_NO_PATHCONV=1 # Git Bash on Windows

[ -f "$DUMP" ] || { echo "no such file: $DUMP" >&2; exit 1; }
case "$TAG" in latest | "") echo "the tag must be a date or a version, not '$TAG'" >&2; exit 1 ;; esac

CTX=$(mktemp -d)
NAME=devdb-publish-$$
ES_NAME=devdb-publish-es-$$
NET=devdb-publish-$$
API_BUILD=devdb-publish-api:$$
native_path() { if command -v cygpath > /dev/null; then cygpath -m "$1"; else echo "$1"; fi; }
cleanup() {
  docker rm -f "$NAME" "$ES_NAME" > /dev/null 2>&1 || true
  docker network rm "$NET" > /dev/null 2>&1 || true
  docker image rm "$API_BUILD" > /dev/null 2>&1 || true
  rm -rf "$CTX"
}
trap cleanup EXIT

cp "$DUMP" "$CTX/c2corg-dev.dump"
cp "$HERE/Dockerfile" "$HERE/restore-dev.sh" "$CTX/"

echo "=== building $IMAGE:$TAG"
docker build -q -t "$IMAGE:$TAG" \
  --label "org.opencontainers.image.source=https://github.com/c2corg/v6_api" \
  --label "org.opencontainers.image.description=Lightweight anonymized database of camptocamp.org, for development" \
  "$(native_path "$CTX")" > /dev/null

echo "=== checking that no personal data is left"
docker run -d --name "$NAME" --memory 1g -e PGCTLTIMEOUT=600 -e POSTGRES_PASSWORD=verify "$IMAGE:$TAG" > /dev/null
# the first server is the temporary one of the initialization (which ends with a message): wait for the final one
server_ready() { # the logs are captured first: `grep -q` in a pipeline would kill it with a SIGPIPE
  local log
  log=$(docker logs "$NAME" 2>&1) || true
  case "$log" in *"init process complete"*) log=${log#*init process complete} ;; *) return 1 ;; esac
  case "$log" in *"ready to accept connections"*) return 0 ;; *) return 1 ;; esac
}
for _ in $(seq 1 600); do
  server_ready && break
  sleep 3
done
server_ready || { echo "the server of the image did not start" >&2; exit 1; }
docker exec -i "$NAME" psql -U postgres -d c2corg -X -q -v ON_ERROR_STOP=1 < "$HERE/60-verify.sql"

echo "=== building the Elasticsearch image (indexing the database with the code of $REPO)"
docker network create "$NET" > /dev/null
docker network connect --alias postgresql "$NET" "$NAME"
docker build -q -t "$API_BUILD" -f "$(native_path "$REPO/docker/Dockerfile.dev")" "$(native_path "$REPO")" > /dev/null
ES_DIR=$CTX/es
mkdir -p "$ES_DIR"
cp "$HERE/Dockerfile.elasticsearch" "$ES_DIR/"
ES_BASE=devdb-publish-es-base:$$
docker build -q --target base -t "$ES_BASE" -f "$(native_path "$ES_DIR/Dockerfile.elasticsearch")" "$(native_path "$ES_DIR")" > /dev/null
trap 'cleanup; docker image rm "$ES_BASE" > /dev/null 2>&1 || true' EXIT

# the data directory is a plain directory of the container, to copy it out when the server is stopped
start_es() { # $1 = image, $2... = options of the server
  local image=$1
  shift
  docker rm -f "$ES_NAME" > /dev/null 2>&1 || true
  docker run -d --name "$ES_NAME" --network "$NET" --network-alias elasticsearch --memory 1536m \
    -e ES_HEAP_SIZE=768m "$image" "$@" > /dev/null
}
# runs a command of the API image on the build network, with a development.ini pointing at the two servers
# (the single quotes are meant: the commands are expanded by the shell of the container)
# shellcheck disable=SC2016
in_api() {
  docker run --rm --network "$NET" -v "$(native_path "$REPO"):/src:ro" "$API_BUILD" sh -ec '
    cat > /tmp/env.build <<ENV
version=0.0.0dev0
db_password=verify
elasticsearch_batch_size_fill_index=250
ENV
    mkdir -p /tmp/cfg && cd /tmp/cfg
    for f in common development; do
      python /src/scripts/env_replace /src/config/env.default /src/config/env.dev /tmp/env.build < /src/$f.ini.in > $f.ini
    done
    ready=
    for _ in $(seq 1 60); do
      python -c "import urllib.request as u; u.urlopen(\"http://elasticsearch:9200\", timeout=3)" 2> /dev/null && ready=1 && break
      sleep 3
    done
    [ -n "$ready" ] || { echo "Elasticsearch did not start" >&2; exit 1; }
    # the shards must be recovered too, or a count made right after the start is partial
    python -c "import urllib.request as u; u.urlopen(\"http://elasticsearch:9200/_cluster/health?wait_for_status=green&timeout=120s\", timeout=130)"
    '"$1"
}

start_es "$ES_BASE" -Des.path.data=/esdata -Des.index.number_of_replicas=0 -Des.script.inline=true
# small batches and retries: a request to a cold Elasticsearch on a loaded machine can exceed the 10 s timeout
# of the client (filling is idempotent, the documents are indexed by id)
# shellcheck disable=SC2016
in_api 'initialize_c2corg_api_es development.ini
  for attempt in 1 2 3; do
    fill_es_index development.ini && break
    [ "$attempt" = 3 ] && exit 1
    echo "fill_es_index failed (attempt $attempt), retrying"
  done
  es_index_fingerprint store development.ini
  # flush to the disk: the data is copied out of a stopped server
  python -c "import urllib.request as u; u.urlopen(u.Request(\"http://elasticsearch:9200/_flush\", method=\"POST\"))"'
# a clean shutdown of Elasticsearch takes more than the 10 s of the default
docker stop -t 60 "$ES_NAME" > /dev/null
docker cp "$ES_NAME:/esdata" "$(native_path "$ES_DIR/esdata")"
docker build -q -t "$ES_IMAGE:$TAG" \
  --label "org.opencontainers.image.source=https://github.com/c2corg/v6_api" \
  --label "org.opencontainers.image.description=Elasticsearch 2.4 indexed from the dev database of the same tag" \
  --label "org.opencontainers.image.version=$TAG" \
  -f "$(native_path "$ES_DIR/Dockerfile.elasticsearch")" "$(native_path "$ES_DIR")" > /dev/null

echo "=== checking the Elasticsearch image"
start_es "$ES_IMAGE:$TAG" elasticsearch -Des.path.data=/esdata -Des.index.number_of_replicas=0 -Des.script.inline=true
in_api 'es_index_fingerprint check development.ini && python -c "
import json, urllib.request as u
count = json.load(u.urlopen(\"http://elasticsearch:9200/c2corg/_count\"))[\"count\"]
print(count, \"documents in the index\")
assert count > 40000, count
"'

if [ -n "${DRY_RUN:-}" ]; then
  echo "dry run: $IMAGE:$TAG and $ES_IMAGE:$TAG built and checked, not pushed"
  exit 0
fi

echo
echo "About to push (${PUSH}): $IMAGE:$TAG and $ES_IMAGE:$TAG, and their \`latest\` ($(du -h "$DUMP" | cut -f1) dump)."
echo "Once pushed, the package is private until it is made public in its settings on GitHub."
read -r -p "Push? [y/N] " answer
[ "$answer" = y ] || { echo "not pushed"; exit 0; }

for kind in $PUSH; do
  case "$kind" in db) image=$IMAGE ;; es) image=$ES_IMAGE ;; *) echo "PUSH: unknown image '$kind'" >&2; exit 1 ;; esac
  docker tag "$image:$TAG" "$image:latest"
  docker push "$image:$TAG"
  docker push "$image:latest"
done
