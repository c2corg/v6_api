#!/bin/sh -e

VERSION=`git rev-parse --short HEAD 2>/dev/null || echo "0"`
REPO="c2corg/v6_api"

if [ "$TRAVIS_PULL_REQUEST" != "false" ]; then
  echo "Not building docker images out of Pull Requests"
  exit 0
fi

git archive --format=tar --output project.tar "$TRAVIS_COMMIT"

if [ "$TRAVIS_BRANCH" = "master" ]; then
  DOCKER_IMAGE="${REPO}:latest"
  DOCKER_SOURCE="branch '${TRAVIS_BRANCH}'"
elif [ ! -z "$TRAVIS_TAG" ]; then
  DOCKER_IMAGE="${REPO}:${TRAVIS_TAG}"
  DOCKER_SOURCE="tag '${TRAVIS_TAG}'"
elif [ ! -z "$TRAVIS_BRANCH" ]; then
  DOCKER_IMAGE="${REPO}:${TRAVIS_BRANCH}"
  DOCKER_SOURCE="branch '${TRAVIS_BRANCH}'"
else
  echo "Don't know how to build image"
  exit 1
fi

echo "Building docker image '${DOCKER_IMAGE}' out of ${DOCKER_SOURCE}"
docker build -t "${DOCKER_IMAGE}"  --build-arg "VERSION=${VERSION}" .
docker inspect "${DOCKER_IMAGE}"
docker history "${DOCKER_IMAGE}"
