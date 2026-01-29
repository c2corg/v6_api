#!/bin/bash

./scripts/env_replace .env < production.ini.in > production.ini

gunicorn --paste production.ini -u www-data -g www-data -b:8080
