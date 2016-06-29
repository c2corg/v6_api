#!/bin/sh -e

cd /var/www
env >> config/dev
make -f config/dev template

