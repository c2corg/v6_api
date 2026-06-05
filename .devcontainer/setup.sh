#!/bin/bash
set -e

echo "==> Installing Python dependencies..."
pip install -e ".[dev]"

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
initialize_c2corg_api_db development.ini || true

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

echo "==> Initializing Elasticsearch indexes..."
fill_es_index development.ini || true

echo ""
echo "============================================="
echo "  Dev container setup complete!"
echo ""
echo "  Run the API:   pserve development.ini --reload"
echo "  Run tests:     pytest"
echo "  Run linter:    flake8 c2corg_api es_migration"
echo "  Or use make:   make test / make serve / make lint"
echo "============================================="
