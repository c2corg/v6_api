#!/bin/sh -ex

cd /var/www

mkdir -p .build/venv 
virtualenv -p python3 .build/venv 
.build/venv/bin/pip install --upgrade pip