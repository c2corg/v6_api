#!/bin/sh

set -xe

su -p -c "pg_dump -Fc -C c2corg" postgres > /share/c2corg-anonymized.dump
