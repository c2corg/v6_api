#!/bin/sh -e

cd /var/www
env >> config/env.prod
make bootstrap
