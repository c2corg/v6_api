#!/bin/sh -e

cd /var/www
echo 'include Makefile' > config/docker
env >> config/docker
make -f config/docker template
