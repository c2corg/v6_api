#!/bin/bash

apt update
apt install -y postgresql-client
cd /c2c_ci
python -V
mkdir ~/.venvs
python -m venv ~/.venvs/ci
source ~/.venvs/ci/bin/activate
pip install --upgrade pip setuptools wheel
pip install dotenv flake8
pip install .[dev]
flake8 c2corg_api es_migration
export PGHOST=postgresql
export PGPORT=5432
export PGUSER=postgres
export PGPASSWORD=test
./scripts/database/create_test_schema.sh
make CONFIG=config/so.test load-env
curl -v http://elasticsearch:9200
pytest --cov-report term --cov-report xml --cov=c2corg_api
