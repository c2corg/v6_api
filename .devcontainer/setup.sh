#!/bin/bash
set -e

echo "==> Installing Python dependencies..."
uv sync --frozen

echo "==> Installing the git pre-commit hook (ruff)..."
uv run --frozen pre-commit install

echo "==> Copying env.local.sample to env.local (if not present)..."
if [ ! -f config/env.local ]; then
  cp config/env.local.sample config/env.local
fi

# Override hosts to point to docker-compose service names
# (inside the devcontainer network, services are reachable by name)
cat > config/env.devcontainer <<'EOF'
#!/bin/sh
version=0.0.0dev0
db_host=postgresql
tests_db_host=postgresql
elasticsearch_host=elasticsearch
redis_url=redis://redis:6379/
EOF

echo "==> Generating config files from templates..."
./scripts/env_replace config/env.default config/env.dev config/env.devcontainer < alembic.ini.in > alembic.ini
./scripts/env_replace config/env.default config/env.dev config/env.devcontainer < common.ini.in > common.ini
./scripts/env_replace config/env.default config/env.dev config/env.devcontainer < development.ini.in > development.ini
./scripts/env_replace config/env.default config/env.dev config/env.devcontainer < test.ini.in > test.ini

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
  echo "  Dev database already initialized"
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
until curl -s http://elasticsearch:9200 > /dev/null 2>&1; do
  echo "  Elasticsearch not ready yet, retrying in 5s..."
  sleep 5
done

echo "==> Initializing the Elasticsearch index..."
# Create the index with its mappings first (it does nothing if the index exists): without it Elasticsearch
# creates the index by itself when documents arrive, without the search mappings, and the search finds nothing.
initialize_c2corg_api_es development.ini

# The Elasticsearch data volume may already contain the index of the dev database. It is kept if it was built
# by this version of the indexing code (the fingerprint stored with it is compared with the one of the code);
# otherwise, or if it is empty, it is rebuilt from the database (about 5 minutes).
ES_COUNT=$(curl -s "http://elasticsearch:9200/c2corg_*/_count" | sed -n 's/.*"count":\([0-9]*\).*/\1/p')
REBUILD=1
if [ "${ES_COUNT:-0}" -gt 0 ]; then
  if es_index_fingerprint check development.ini; then
    echo "  The index contains ${ES_COUNT} documents and is up to date"
    REBUILD=
  else
    echo "  Rebuilding the index with the current indexing code"
    # one index per document type; ES refuses to delete them with a wildcard
    for doc_type in a b c i m o r u w x; do
      curl -s -XDELETE "http://elasticsearch:9200/c2corg_${doc_type}" > /dev/null
    done
    initialize_c2corg_api_es development.ini
  fi
fi

if [ -n "$REBUILD" ]; then
  # The first request often times out on a cold Elasticsearch, hence the retries.
  for attempt in 1 2 3; do
    fill_es_index development.ini && break
    if [ "$attempt" = 3 ]; then
      echo "  fill_es_index failed 3 times: run it again by hand (fill_es_index development.ini)" >&2
      exit 1
    fi
    echo "  fill_es_index failed (attempt ${attempt}), retrying in 10s..."
    sleep 10
  done
  es_index_fingerprint store development.ini
fi

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
