#!/bin/bash
set -e

echo "==> Installing Python dependencies..."
uv sync --frozen

echo "==> Installing the git pre-commit hook (ruff)..."
uv run --frozen pre-commit install

echo "==> Generating config files from templates..."
make CONFIG=config/env.devcontainer load-env

echo "==> Waiting for PostgreSQL to be ready..."
until pg_isready -h postgresql -U postgres; do
  echo "  PostgreSQL not ready yet, retrying in 2s..."
  sleep 2
done

echo "==> Initializing dev database..."
export PGPASSWORD=test
export PGUSER=postgres
export PGHOST=postgresql
export POSTGRES_USER=postgres

# Create dev database (adapted from scripts/database/create_schema.sh)
DBNAME="c2corg"
if psql -tAc "SELECT 1 FROM pg_database WHERE datname='${DBNAME}'" | grep -q 1; then
  echo "  Dev database already exists: ${DBNAME}"
else
  echo "  Creating dev database: ${DBNAME}"
  psql -v ON_ERROR_STOP=1 --username "$PGUSER" <<SQL
CREATE DATABASE ${DBNAME} OWNER "postgres";
\c ${DBNAME}
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE SCHEMA IF NOT EXISTS guidebook AUTHORIZATION "postgres";
CREATE SCHEMA IF NOT EXISTS users AUTHORIZATION "postgres";
CREATE SCHEMA IF NOT EXISTS sympa AUTHORIZATION "postgres";
CREATE SCHEMA IF NOT EXISTS alembic AUTHORIZATION "postgres";
SQL
fi
# Only on a fresh database: initialize_c2corg_api_db is not idempotent (it inserts the default langs).
# Not "|| true": a failure here leaves an empty database, and the API then fails on every request.
if psql -d "${DBNAME}" -tAc "SELECT 1 FROM alembic.alembic_version" > /dev/null 2>&1; then
  # The image of the dev database is at the alembic revision of the code it was published with: bring it to
  # the one of this checkout (it does nothing when it is already there).
  echo "  Dev database already initialized, migrating it to the latest revision"
  alembic upgrade head
else
  initialize_c2corg_api_db development.ini
fi

# Create test database (adapted from scripts/database/create_test_schema.sh)
echo "==> Initializing test database..."
DBNAME="c2corg_tests"
if psql -tAc "SELECT 1 FROM pg_database WHERE datname='${DBNAME}'" | grep -q 1; then
  echo "  Test database already exists: ${DBNAME}"
else
  echo "  Creating test database: ${DBNAME}"
  psql -v ON_ERROR_STOP=1 --username "$PGUSER" <<SQL
CREATE DATABASE ${DBNAME} OWNER "postgres";
\c ${DBNAME}
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE SCHEMA IF NOT EXISTS guidebook AUTHORIZATION "postgres";
CREATE SCHEMA IF NOT EXISTS users AUTHORIZATION "postgres";
CREATE SCHEMA IF NOT EXISTS sympa AUTHORIZATION "postgres";
CREATE SCHEMA IF NOT EXISTS alembic AUTHORIZATION "postgres";
SQL
fi

echo "==> Waiting for Elasticsearch to be ready..."
until curl -fsS 'http://elasticsearch:9200/_cluster/health?wait_for_status=yellow&timeout=4s' > /dev/null; do
  echo "  Elasticsearch not ready yet, retrying in 5s..."
  sleep 5
done

echo "==> Initializing the Elasticsearch index..."
make ES_INDEX_URL=http://elasticsearch:9200/c2corg init-elastic

echo ""
echo "============================================="
echo "  Dev container setup complete!"
echo ""
echo "  Log in with the account moderator, user... (password: c2c)"
echo "  Run the API:   C2C_API_CONFIG=development.ini uvicorn c2corg_api.asgi:app --reload --host 0.0.0.0 --port 6543"
echo "  Run tests:     pytest"
echo "  Run linter:    ruff check c2corg_api es_migration"
echo "  Format code:   make format (also done on save in VS Code)"
echo "  Or use make:   make test / make serve / make lint"
echo "============================================="
