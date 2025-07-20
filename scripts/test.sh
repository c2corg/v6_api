#!/bin/bash

docker-compose exec -u postgres -T postgresql /v6_api/scripts/create_user_db_test.sh
docker-compose exec api make -f config/docker-dev test