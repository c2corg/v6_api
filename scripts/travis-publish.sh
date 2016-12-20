#!/bin/sh -e

REPO="c2corg/v6_api"

if [ "$TRAVIS_PULL_REQUEST" != "false" ]; then
  echo "Not publishing docker images out of Pull Requests"
  exit 0
fi

docker login -u "$DOCKER_USER" -p "$DOCKER_PASS"

if [ "$TRAVIS_BRANCH" = "master" ]; then
  DOCKER_IMAGE="${REPO}:latest"
elif [ ! -z "$TRAVIS_TAG" ]; then
  DOCKER_IMAGE="${REPO}:${TRAVIS_TAG}"
elif [ ! -z "$TRAVIS_BRANCH" ]; then
  DOCKER_IMAGE="${REPO}:${TRAVIS_BRANCH}"
else
  echo "Not pushing any image"
fi

echo "Pushing image '${DOCKER_IMAGE}' to docker hub"
docker push "${DOCKER_IMAGE}"
