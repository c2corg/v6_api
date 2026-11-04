# Dev Container for c2corg v6_api

This directory contains a [Dev Container](https://containers.dev/) configuration
that provides a fully configured development environment with all services
(PostgreSQL/PostGIS, Elasticsearch, Redis) running as companion containers.

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or a compatible Docker engine)
- [VS Code](https://code.visualstudio.com/) with the [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)

## Getting started

1. Open this repository in VS Code
2. When prompted, click **"Reopen in Container"** — or use the command palette:
   `Dev Containers: Reopen in Container`
3. Wait for the container to build and the `postCreateCommand` setup script to
   finish (first run takes a few minutes)
4. You're ready to go!

## What's included

| Service        | Hostname        | Port |
|----------------|-----------------|------|
| PostgreSQL     | `postgresql`    | 5432 |
| Elasticsearch  | `elasticsearch` | 9200 |
| Redis          | `redis`         | 6379 |
| API (when run) | `localhost`     | 6543 |

All ports are forwarded to your host machine for convenience.

## The data

The development database is a lightweight anonymized extract of the production data (about 45,000
documents, a few hundred accounts, the stop areas), restored at the first start from the image
`ghcr.io/c2corg/c2corg-dev-db` (PostgreSQL 18 + PostGIS). See
[`scripts/dev-database`](../scripts/dev-database/README.md) for what it contains and how it is built.

- Accounts (password `c2c` for all): `moderator`, `user`, `blocked`, `unvalidated`.
- Elasticsearch comes from the image `ghcr.io/c2corg/c2corg-dev-es`, published with the database and
  already indexed. The setup script keeps that index if it was built by the same indexing code as your
  checkout (see `es_index_fingerprint`); otherwise it rebuilds it from the database (a few minutes). The
  data of both services lives in the Docker volumes `postgres_data` and `es_data`.
- To get a fresh database and index, rebuild the container after removing these two volumes (the
  names are prefixed by the Compose project): `docker volume rm <project>_postgres_data <project>_es_data`.
- Newer images are used after removing the two volumes and pulling them
  (`docker compose pull postgresql elasticsearch`).

## Common commands

```bash
# Run the test suite
pytest

# Run a specific test file
pytest c2corg_api/tests/models/test_book.py

# Format the code, then run the linter (also: make format / make lint)
ruff format c2corg_api es_migration
ruff check c2corg_api es_migration

# Start the API server (with auto-reload)
C2C_API_CONFIG=development.ini uvicorn c2corg_api.asgi:app --reload --host 0.0.0.0 --port 6543

# Or use make targets
make test
make serve
make lint
```

## Rebuilding

If dependencies change, rebuild the container:

- Command palette → `Dev Containers: Rebuild Container`

## Troubleshooting

- **Database errors**: The development database comes with the image and the setup script creates the
  test database. If you need to re-run:

  ```bash
  PGPASSWORD=test PGUSER=postgres PGHOST=postgresql \
    bash .devcontainer/setup.sh
  ```

- **Elasticsearch not ready**: The setup script waits for ES, but if tests
  fail with connection errors, check: `curl http://elasticsearch:9200`

- **The search finds nothing**: the index was created without its mappings or is empty. Delete it and
  run the setup again: `curl -XDELETE http://elasticsearch:9200/c2corg && bash .devcontainer/setup.sh`

- **Config out of date**: Re-generate config files:

  ```bash
  bash .devcontainer/setup.sh
  ```
