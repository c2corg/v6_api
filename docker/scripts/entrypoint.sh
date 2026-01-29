#!/bin/bash

set -e

./scripts/env_replace config/env.default .env < production.ini.in > production.ini
./scripts/env_replace config/env.default .env < common.ini.in > common.ini

gunicorn --paste production.ini -u www-data -g www-data -b:8080
