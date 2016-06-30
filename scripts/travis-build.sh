#!/bin/sh -e

REPO="c2corg/v6_api"

if [ "$TRAVIS_PULL_REQUEST" != "false" ]; then
  echo "Not building docker images out of Pull Requests"
  exit 0
fi

if [ "$TRAVIS_BRANCH" = "master" ]; then
  echo "Building image '${REPO}:latest'"
  docker build -t "${REPO}:latest" .
elif [ ! -z "$TRAVIS_TAG" ]; then
  echo "Building image '${REPO}:${TRAVIS_TAG}'"
  docker build -t "${REPO}:${TRAVIS_TAG}" .
elif [ ! -z "$TRAVIS_BRANCH" ]; then
  echo "Building image '${REPO}:${TRAVIS_BRANCH}'"
  docker build -t "${REPO}:${TRAVIS_BRANCH}" .
else
  echo "Don't know how to build image"
  exit 1
fi
