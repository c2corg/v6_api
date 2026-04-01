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

## Common commands

```bash
# Run the test suite
pytest

# Run a specific test file
pytest c2corg_api/tests/models/test_book.py

# Run the linter
flake8 c2corg_api es_migration

# Start the API server (with auto-reload)
pserve development.ini --reload

# Or use make targets
make test
make serve
make lint
```

## Rebuilding

If dependencies change, rebuild the container:

- Command palette → `Dev Containers: Rebuild Container`

## Troubleshooting

- **Database errors**: The setup script creates both databases automatically. If you need to re-run:

  ```bash
  PGPASSWORD=test PGUSER=postgres PGHOST=postgresql \
    bash .devcontainer/setup.sh
  ```

- **Elasticsearch not ready**: The setup script waits for ES, but if tests
  fail with connection errors, check: `curl http://elasticsearch:9200`

- **Config out of date**: Re-generate config files:

  ```bash
  bash .devcontainer/setup.sh
  ```
