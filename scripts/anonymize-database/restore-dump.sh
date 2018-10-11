#!/bin/sh

set -xe

DUMP="$(ls /share/c2corg.*.dump)"

test -f "$DUMP"

su -p -c "pg_restore -v -d c2corg ${DUMP}" postgres || true
