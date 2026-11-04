#!/bin/bash
# Builds the Elasticsearch image of the dev database, with its index already filled, checks it and pushes it
# to the GitHub container registry, with the same tag as the database image it was filled from.
#
#   publish-es.sh <tag of the database image>        e.g. publish-es.sh 2026-07-19
#
# 1. starts the database image and an empty Elasticsearch in a throwaway network, 2. creates and fills the
# index with the API image (initialize_c2corg_api_es, then fill_es_index), 3. stops Elasticsearch and copies
# its data into the image, 4. starts the image and checks the index, 5. asks for confirmation, 6. pushes <tag>
# and `latest`.
#
# The index mapping comes from the code of the API image: publish again when it changes.
# Needs `docker login ghcr.io` with a token which can write packages. A package created by a push is
# private: making it public is done in the package settings on GitHub, it cannot be done from here.
#
# Variables: IMAGE (default ghcr.io/c2corg/c2corg-dev-es), DB_IMAGE (default ghcr.io/c2corg/c2corg-dev-db),
# API_IMAGE (default ghcr.io/c2corg/v6_api:latest), LICENSE (SPDX id put in the image labels),
# MIN_DOCS (the check fails below this number of indexed documents, default 10000), DRY_RUN=1 to stop
# before the push, KEEP=1 to keep the containers and the network when the build ends (to inspect a failure).

set -euo pipefail

TAG=${1:?usage: publish-es.sh <tag of the database image>}
IMAGE=${IMAGE:-ghcr.io/c2corg/c2corg-dev-es}
DB_IMAGE=${DB_IMAGE:-ghcr.io/c2corg/c2corg-dev-db}
API_IMAGE=${API_IMAGE:-ghcr.io/c2corg/v6_api:latest}
LICENSE=${LICENSE:-CC-BY-SA-3.0}
MIN_DOCS=${MIN_DOCS:-10000}
HERE=$(cd "$(dirname "$0")" && pwd)
export MSYS_NO_PATHCONV=1 # Git Bash on Windows

case "$TAG" in latest | "") echo "the tag must be the one of a database image, not '$TAG'" >&2; exit 1 ;; esac

CTX=$(mktemp -d)
NAME=deves-publish-$$
NET=$NAME
VOLUME=$NAME-data
cleanup() {
  rm -rf "$CTX"
  if [ -n "${KEEP:-}" ]; then
    echo "kept for inspection: containers $NAME-db, $NAME-es, $NAME-check, network $NET, volume $VOLUME" >&2
    return
  fi
  docker rm -f "$NAME-db" "$NAME-es" "$NAME-check" > /dev/null 2>&1 || true
  docker network rm "$NET" > /dev/null 2>&1 || true
  docker volume rm "$VOLUME" > /dev/null 2>&1 || true
  docker rmi "$NAME-empty" > /dev/null 2>&1 || true
}
trap cleanup EXIT
native() { if command -v cygpath > /dev/null; then cygpath -m "$1"; else echo "$1"; fi; }

docker pull -q "$DB_IMAGE:$TAG" > /dev/null
docker pull -q "$API_IMAGE" > /dev/null
API_DIGEST=$(docker image inspect -f '{{index .RepoDigests 0}}' "$API_IMAGE")
cp "$HERE/Dockerfile.es" "$CTX/Dockerfile"
mkdir "$CTX/esdata"

echo "=== starting $DB_IMAGE:$TAG and an empty Elasticsearch"
docker build -q --target empty -t "$NAME-empty" "$(native "$CTX")" > /dev/null
docker network create "$NET" > /dev/null
docker run -d --name "$NAME-db" --network "$NET" --network-alias db --memory 1g \
  -e POSTGRES_PASSWORD=build "$DB_IMAGE:$TAG" > /dev/null
# the index goes to a volume, read once Elasticsearch is stopped (`docker cp` from a stopped container hangs
# with some Docker engines)
docker run -d --name "$NAME-es" --network "$NET" --network-alias es --memory 1g \
  -e ES_HEAP_SIZE=512m -v "$VOLUME":/usr/share/elasticsearch/baked "$NAME-empty" > /dev/null

# the first server is the temporary one of the initialization (which ends with a message): wait for the final one
server_ready() { # the logs are captured first: `grep -q` in a pipeline would kill it with a SIGPIPE
  local log
  log=$(docker logs "$NAME-db" 2>&1) || true
  case "$log" in *"init process complete"*) log=${log#*init process complete} ;; *) return 1 ;; esac
  case "$log" in *"ready to accept connections"*) return 0 ;; *) return 1 ;; esac
}
for _ in $(seq 1 200); do
  server_ready && break
  sleep 3
done
server_ready || { echo "the database did not start" >&2; exit 1; }
es() { docker exec "$1" wget -qO- "http://localhost:9200$2"; }
for _ in $(seq 1 60); do
  es "$NAME-es" / > /dev/null 2>&1 && break
  sleep 2
done
es "$NAME-es" / > /dev/null || { docker logs "$NAME-es" 2>&1 | tail -20 >&2; echo "Elasticsearch did not start" >&2; exit 1; }

echo "=== filling the index with $API_DIGEST"
# the entrypoint of the API image writes production.ini from these variables
api() {
  docker run --rm --network "$NET" \
    -e db_host=db -e db_user=www-data -e db_password=www-data -e db_name=c2corg \
    -e elasticsearch_host=es -e elasticsearch_index=c2corg \
    "$API_IMAGE" "$@"
}
# in this order: without the first one, Elasticsearch creates the index on its own without the search
# sub-fields, and the search silently returns nothing
api initialize_c2corg_api_es production.ini
api fill_es_index production.ini

# a clean stop flushes the index to disk
docker stop -t 60 "$NAME-es" > /dev/null
docker run --rm -v "$VOLUME":/baked:ro "$NAME-empty" tar -C /baked -cf - . | tar -C "$CTX/esdata" -xf -

echo "=== building $IMAGE:$TAG"
docker build -q -t "$IMAGE:$TAG" \
  --label "org.opencontainers.image.source=https://github.com/c2corg/v6_api" \
  --label "org.opencontainers.image.description=Elasticsearch index of the lightweight anonymized database of camptocamp.org ($DB_IMAGE:$TAG), for development" \
  --label "org.opencontainers.image.licenses=$LICENSE" \
  --label "org.c2corg.dev-db=$DB_IMAGE:$TAG" \
  --label "org.c2corg.api=$API_DIGEST" \
  "$(native "$CTX")" > /dev/null

echo "=== checking the index of the image"
docker run -d --name "$NAME-check" --memory 1g -e ES_HEAP_SIZE=512m "$IMAGE:$TAG" > /dev/null
for _ in $(seq 1 60); do
  es "$NAME-check" '/_cluster/health?wait_for_status=yellow&timeout=2s' 2>/dev/null | grep -q '"status":"\(yellow\|green\)"' && break
  sleep 2
done
COUNT=$(es "$NAME-check" /c2corg/_count | sed -n 's/.*"count":\([0-9]*\).*/\1/p')
echo "$COUNT documents"
[ "${COUNT:-0}" -ge "$MIN_DOCS" ] || { echo "fewer than $MIN_DOCS documents" >&2; exit 1; }
# the n-gram sub-field exists only when the index was created by initialize_c2corg_api_es
HITS=$(es "$NAME-check" '/c2corg/_search?size=0&q=title_fr.ngram:mont' | sed -n 's/.*"hits":{"total":\([0-9]*\).*/\1/p')
echo "$HITS documents found by a search on title_fr.ngram"
[ "${HITS:-0}" -gt 0 ] || { echo "the search finds nothing: the index has no search sub-fields" >&2; exit 1; }

if [ -n "${DRY_RUN:-}" ]; then
  echo "dry run: $IMAGE:$TAG built and checked, not pushed"
  exit 0
fi

echo
echo "About to push $IMAGE:$TAG and $IMAGE:latest ($COUNT documents)."
echo "Once pushed, the package is private until it is made public in its settings on GitHub."
read -r -p "Push? [y/N] " answer
[ "$answer" = y ] || { echo "not pushed"; exit 0; }

docker tag "$IMAGE:$TAG" "$IMAGE:latest"
docker push "$IMAGE:$TAG"
docker push "$IMAGE:latest"
