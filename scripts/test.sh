#!/bin/bash

docker-compose exec api make -f config/docker-dev test
