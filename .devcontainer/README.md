# Dev Container for c2corg v6_api

The setup (with or without VS Code), Podman, the configuration and the daily commands are in the
[main README](../README.md#getting-started-dev-container-recommended). The root `docker-compose.yml`
belongs to the [manual setup](../HOWTO-MANUAL-DEV.md): do not start both stacks.

## Files

- `devcontainer.json`: the VS Code integration; runs `setup.sh` once the container is created.
- `docker-compose.yml`: the app container and its services. Only the API port 6543 is published, on
  `127.0.0.1`; VS Code also forwards the ports of the services.
- `Dockerfile`: Python and the system tools. uv installs the dependencies in `/opt/venv`, outside the
  bind-mounted workspace.
- `setup.sh`: idempotent setup (dependencies, `*.ini` files with `config/env.devcontainer`, database
  migration, test database, `make init-elastic`).

## Troubleshooting

In the app container:

- Anything failed or looks out of date (configuration, database revision): `bash .devcontainer/setup.sh`.
- Elasticsearch unreachable: `curl http://elasticsearch:9200/_cluster/health`.
- The search finds nothing: `make init-elastic` rebuilds the index when it is empty or was built by
  another version of the indexing code.
- `fill_es_index` times out on a cold or emulated Elasticsearch: the setup retries it three times;
  run `make init-elastic` again if it still fails.
