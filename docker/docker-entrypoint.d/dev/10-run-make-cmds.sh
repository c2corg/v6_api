#!/bin/sh -ex

cd /var/www
make -f config/docker-dev install 
make -f config/docker-dev .build/dev-requirements.timestamp 
py3compile -f .build/venv/ 
rm -fr .cache 
make -f config/docker-dev template