#!/bin/bash

set -e

./scripts/env_replace config/env.default --keep-env .env < production.ini.in > production.ini
./scripts/env_replace config/env.default --keep-env .env < common.ini.in > common.ini

exec "$@"
