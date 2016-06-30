#!/bin/sh -e

REPO="c2corg/v6_api"

docker login -e "$DOCKER_EMAIL" -u "$DOCKER_USER" -p "$DOCKER_PASS"

if [ "$TRAVIS_BRANCH" = "master" ]; then
  echo "Pushing image '${REPO}:latest' to docker hub"
  docker push "${REPO}:latest"
elif [ ! -z "$TRAVIS_TAG" ] && [ "$TRAVIS_PULL_REQUEST" = "false" ]; then
  echo "Pushing image '${REPO}:${TRAVIS_TAG}' to docker hub"
  docker push "${REPO}:${TRAVIS_TAG}"
elif [ ! -z "$TRAVIS_BRANCH" ] && [ "$TRAVIS_PULL_REQUEST" = "false" ]; then
  echo "Pushing image '${REPO}:${TRAVIS_BRANCH}' to docker hub"
  docker push "${REPO}:${TRAVIS_BRANCH}"
else
  echo "Not pushing any image"
fi
