#!/bin/bash

docker-compose exec -u postgres -T postgresql /v6_api/scripts/create_user_db_test.sh
docker-compose exec api .build/venv/bin/pytest --cov-report term --cov-report xml ${@:-"--cov=c2corg_api"}
