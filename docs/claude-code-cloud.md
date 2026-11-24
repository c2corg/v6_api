# Dev stack in Claude Code on the web (restricted sandboxes)

The [dev container stack](../README.md#getting-started-dev-container-recommended) runs unchanged in a
Claude Code cloud environment (Docker is available), but two sandbox restrictions need a workaround,
which `.devcontainer/docker-compose.sandbox.yml` provides. The "demo database" is the anonymized dev
database (`ghcr.io/c2corg/c2corg-dev-db`) with its Elasticsearch index: restored at the first start.

Only `c2corg/v6_api` and `c2corg/c2c_ui` are needed; the infra repo (`docker_compose`, CD) is not.

## One command

```bash
git clone https://github.com/c2corg/v6_api && git clone https://github.com/c2corg/c2c_ui
cd v6_api && scripts/sandbox-up.sh
```

It starts the services, runs `setup.sh`, serves the API on <http://localhost:6543> and, if `../c2c_ui`
exists (or `UI_DIR`), the UI on <http://localhost:8080> against it (`C2C_BACKEND=localhost`). Log in
with `moderator` or `user`, password `c2c`. The first run pulls ~2 GB of images and takes several minutes.

## What the sandbox override fixes

| Symptom | Cause | Fix in `docker-compose.sandbox.yml` |
| --- | --- | --- |
| `error setting rlimit type 7: operation not permitted` when starting elasticsearch | the sandbox refuses the raised `nofile` ulimit | `ulimits` reset (Elasticsearch only warns: `discovery.type=single-node` skips the bootstrap checks) |
| `uv`: `invalid peer certificate: UnknownIssuer` in `setup.sh` | the egress proxy re-signs TLS | mounts the CA bundle (`CCR_CA_BUNDLE`, default `/root/.ccr/ca-bundle.crt`) and sets `SSL_CERT_FILE` (and similar variables) |

Other containers named `c2c-db` / `c2c-es` may already exist in the environment: they are unrelated
(no published ports); leave them.

## The `.env` file

`.env` is tracked in git and loaded by the app container (`env_file`). It holds the Navitia
(public transport) settings; in dev `NAVITIA_API_KEY="test-key"` is a placeholder.

- If `.env` is missing, `docker compose` refuses to start: `git checkout .env`.
- If `NAVITIA_API_KEY` is empty/unset, or the `test-key` placeholder, the API logs a **warning at
  startup**; the "public transport access" features (journeys, nearby stops of new waypoints) do not
  work, which is expected unless you set a real key in `.env` (do not commit it).
- `scripts/sandbox-up.sh` warns if `.env` or the CA bundle is missing.

## Daily commands

```bash
DC="docker compose -p v6-api-dev -f .devcontainer/docker-compose.yml -f .devcontainer/docker-compose.sandbox.yml"
$DC exec app bash        # shell in the app container (tests: pytest, lint: make lint)
$DC stop                 # stop, keeping the data
```

The stack is lost when the cloud container is reclaimed: run `scripts/sandbox-up.sh` again.
