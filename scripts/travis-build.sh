#!/bin/sh -e

REPO="c2corg/v6_api"

if [ "$TRAVIS_BRANCH" = "master" ]; then
  echo "Building image '${REPO}:latest'"
  docker build -t "${REPO}:latest" .
elif [ ! -z "$TRAVIS_TAG" ] && [ "$TRAVIS_PULL_REQUEST" = "false" ]; then
  echo "Building image '${REPO}:${TRAVIS_TAG}'"
  docker build -t "${REPO}:${TRAVIS_TAG}" .
elif [ ! -z "$TRAVIS_BRANCH" ] && [ "$TRAVIS_PULL_REQUEST" = "false" ]; then
  echo "Building image '${REPO}:${TRAVIS_BRANCH}'"
  docker build -t "${REPO}:${TRAVIS_BRANCH}" .
else
  echo "Don't know how to build image"
  exit 1
fi
