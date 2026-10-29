#!/bin/bash
# Builds the dev database image from a dump, checks it and pushes it to the GitHub container registry.
#
#   publish.sh <dump made by build.sh> <tag>        e.g. publish.sh c2corg-dev-pg96.dump 2026-07-19
#
# 1. builds the image locally, 2. starts it and runs 60-verify.sql (no personal data left),
# 3. asks for confirmation, 4. pushes <tag> and `latest`.
#
# Needs `docker login ghcr.io` with a token which can write packages. A package created by a push is
# private: making it public is done in the package settings on GitHub, it cannot be done from here.
#
# Variables: IMAGE (default ghcr.io/c2corg/c2corg-dev-db), LICENSE (SPDX id put in the image labels,
# check it against the terms of use of the site), DRY_RUN=1 to stop before the push.

set -euo pipefail

DUMP=${1:?usage: publish.sh <dump> <tag>}
TAG=${2:?usage: publish.sh <dump> <tag>}
IMAGE=${IMAGE:-ghcr.io/c2corg/c2corg-dev-db}
LICENSE=${LICENSE:-CC-BY-SA-3.0}
HERE=$(cd "$(dirname "$0")" && pwd)
export MSYS_NO_PATHCONV=1 # Git Bash on Windows

[ -f "$DUMP" ] || { echo "no such file: $DUMP" >&2; exit 1; }
case "$TAG" in latest | "") echo "the tag must be a date or a version, not '$TAG'" >&2; exit 1 ;; esac

CTX=$(mktemp -d)
NAME=devdb-publish-$$
trap 'docker rm -f "$NAME" > /dev/null 2>&1 || true; rm -rf "$CTX"' EXIT

cp "$DUMP" "$CTX/c2corg-dev.dump"
cp "$HERE/Dockerfile" "$HERE/restore-dev.sh" "$CTX/"

echo "=== building $IMAGE:$TAG"
docker build -q -t "$IMAGE:$TAG" \
  --label "org.opencontainers.image.source=https://github.com/c2corg/v6_api" \
  --label "org.opencontainers.image.description=Lightweight anonymized database of camptocamp.org for development" \
  --label "org.opencontainers.image.licenses=$LICENSE" \
  "$(if command -v cygpath > /dev/null; then cygpath -m "$CTX"; else echo "$CTX"; fi)" > /dev/null

echo "=== checking that no personal data is left"
docker run -d --name "$NAME" --memory 1g -e POSTGRES_PASSWORD=verify "$IMAGE:$TAG" > /dev/null
# the first server is the temporary one of the initialization (which ends with a message): wait for the final one
server_ready() { # the logs are captured first: `grep -q` in a pipeline would kill it with a SIGPIPE
  local log
  log=$(docker logs "$NAME" 2>&1) || true
  case "$log" in *"init process complete"*) log=${log#*init process complete} ;; *) return 1 ;; esac
  case "$log" in *"ready to accept connections"*) return 0 ;; *) return 1 ;; esac
}
for _ in $(seq 1 200); do
  server_ready && break
  sleep 3
done
server_ready || { echo "the server of the image did not start" >&2; exit 1; }
docker exec -i "$NAME" psql -U postgres -d c2corg -X -q -v ON_ERROR_STOP=1 < "$HERE/60-verify.sql"

if [ -n "${DRY_RUN:-}" ]; then
  echo "dry run: $IMAGE:$TAG built and checked, not pushed"
  exit 0
fi

echo
echo "About to push $IMAGE:$TAG and $IMAGE:latest ($(du -h "$DUMP" | cut -f1) dump)."
echo "Once pushed, the package is private until it is made public in its settings on GitHub."
read -r -p "Push? [y/N] " answer
[ "$answer" = y ] || { echo "not pushed"; exit 0; }

docker tag "$IMAGE:$TAG" "$IMAGE:latest"
docker push "$IMAGE:$TAG"
docker push "$IMAGE:latest"
