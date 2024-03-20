#!/bin/sh -ex

cd /var/www
make -f config/dev install 
py3compile -f .build/venv/ 
rm -fr .cache 