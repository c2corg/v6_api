#!/bin/sh -e

REPO="c2corg/v6_api"

if [ "$TRAVIS_PULL_REQUEST" != "false" ]; then
  echo "Not publishing docker images out of Pull Requests"
  exit 0
fi

docker login -u "$DOCKER_USER" -p "$DOCKER_PASS"

if [ "$TRAVIS_BRANCH" = "master" ]; then
  echo "Pushing image '${REPO}:latest' to docker hub"
  docker push "${REPO}:latest"
elif [ ! -z "$TRAVIS_TAG" ]; then
  echo "Pushing image '${REPO}:${TRAVIS_TAG}' to docker hub"
  docker push "${REPO}:${TRAVIS_TAG}"
elif [ ! -z "$TRAVIS_BRANCH" ]; then
  echo "Pushing image '${REPO}:${TRAVIS_BRANCH}' to docker hub"
  docker push "${REPO}:${TRAVIS_BRANCH}"
else
  echo "Not pushing any image"
fi
