# [camptocamp.org](https://www.camptocamp.org) API developer manual

There are two ways to set up your development environment:

1. **[Dev Container](#option-1-dev-container-recommended)** — the recommended approach; everything runs inside a pre-configured container, no local Python install required.
2. **[Manual setup](#option-2-manual-setup)** — set up Python, services, and configuration by hand on your host machine.

> **Note:** For details on the "Mobilité douce" (public transport) features, see [SMART-ORIGIN-README.md](SMART-ORIGIN-README.md).

---

## Option 1: Dev Container (recommended)

A [Dev Container](https://containers.dev/) configuration is provided in the `.devcontainer/` directory. It gives you a fully configured development environment with all companion services (PostgreSQL/PostGIS, Elasticsearch, Redis) running as side containers.

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or a compatible Docker engine with Docker Compose)
- [VS Code](https://code.visualstudio.com/) with the [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)

### Getting started

1. Clone the repository and open it in VS Code:

   ```sh
   git clone https://github.com/c2corg/v6_api
   cd v6_api
   code .
   ```

2. When prompted, click **"Reopen in Container"** — or open the command palette (`Ctrl+Shift+P` / `Cmd+Shift+P`) and select:

   ```
   Dev Containers: Reopen in Container
   ```

3. Wait for the container to build and the `postCreateCommand` setup script to finish. On the first run this takes a few minutes — it will:
   - Install all Python dependencies
   - Generate the configuration files
   - Create and initialize both the dev and test databases
   - Populate the Elasticsearch indexes

4. You're ready to go! See [Running the API](#running-the-api), [Running tests](#running-tests), and [Linting](#linting) below.

### Services available in the dev container

| Service        | Hostname        | Port |
|----------------|-----------------|------|
| PostgreSQL     | `postgresql`    | 5432 |
| Elasticsearch  | `elasticsearch` | 9200 |
| Redis          | `redis`         | 6379 |
| API (when run) | `localhost`     | 6543 |

All ports are forwarded to your host machine automatically.

### Rebuilding the dev container

If dependencies or the Dockerfile change, rebuild via the command palette:

```
Dev Containers: Rebuild Container
```

Or to re-run the setup script without rebuilding:

```bash
bash .devcontainer/setup.sh
```

For more details, see [`.devcontainer/README.md`](.devcontainer/README.md).

---

## Option 2: Manual setup

### Requirements

- A computer running Linux or Windows (on Windows, take a look at [WSL](https://learn.microsoft.com/fr-fr/windows/wsl/install), it will make your developer life easier). Maybe MacOs can work, but it was not tested.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) 0.13 or newer, which installs the right Python version (3.15) and all dependencies for you
- A docker environment with docker compose plugin (either [docker desktop](https://www.docker.com/products/docker-desktop/) or a manual installation)
- A development IDE is not mandatory, but highly recommended (pycharm, vscode...)
- If you have GNU make installed, you can use it to run all the commands below to initialize and run your development environment (run `make help` to see what can be done) instead of running them "by hand"

### Installing the development environment

- Clone the git repository
- Cd inside your cloned repo
- Install Python and the dependencies (pinned in `uv.lock`) in a `.venv` virtual environment, and the git pre-commit hook:

```shell
make install   # or: uv sync && uv run pre-commit install
```

- Activate the virtual environment (⚠️ Do not forget to activate it in all terminal instances you intend to use), or prefix commands with `uv run`:

```shell
# Linux (or WSL)
source .venv/bin/activate
# Or Windows Powershell
.\.venv\Scripts\Activate.ps1
```

- To add or upgrade a dependency, edit `pyproject.toml` and run `uv lock`, then commit both files.

- Start the necessary tools (postgres database, redis, and elasticsearch) in docker containers:

```shell
docker compose up -d
```

- Go to the config directory and copy the `env.local.sample` to `env.local`
- You should not need to modify it as it is already filled with the necessary values to be compatible with the docker compose defaults but if necessary you can
- Update the `*.ini` file:

```shell
# Linux or WSL
./scripts/env_replace config/env.default config/env.dev config/env.local < alembic.ini.in > alembic.ini
./scripts/env_replace config/env.default config/env.dev config/env.local < common.ini.in > common.ini
./scripts/env_replace config/env.default config/env.dev config/env.local < development.ini.in > development.ini
# Or Windows Powershell (Yes you should really have a look at WSL)
Get-Content alembic.ini.in | cmd /c "python .\scripts\env_replace config/env.default config/env.dev config/env.local > alembic.ini"
Get-Content common.ini.in | cmd /c "python .\scripts\env_replace config/env.default config/env.dev config/env.local > common.ini"
Get-Content development.ini.in | cmd /c "python .\scripts\env_replace config/env.default config/env.dev config/env.local > development.ini"
```

- Initialize database:

```shell
docker compose exec -u postgres -T postgresql /v6_api/scripts/database/create_schema.sh
initialize_c2corg_api_db development.ini
```

- Initialize test database:

```shell
docker compose exec -u postgres -T postgresql /v6_api/scripts/database/create_test_schema.sh
```

- Initialize elastic search indexes

```shell
fill_es_index development.ini
```

## Running the API

- Make sure the postgres redis and elasticsearch docker containers are running

```shell
docker ps
```

- If you do not see them running, restart them (without the initialization steps that should have been done just once when setting up the environment):

```shell
docker compose up -d
```

- Run the API (this command will not exit so you should run it in a separate terminal):

```shell
gunicorn --paste development.ini --reload --bind 0.0.0.0:6543
```

- Run background jobs (run each of these commands in a separate terminal, as they will not exit):

```shell
python c2corg_api/scripts/es/syncer.py development.ini
# Does not work in Windows, as it uses signal.pause() which is only available in unix based OSes (Did I already tell you that you should really look at WSL ?)
python c2corg_api/scripts/jobs/scheduler.py development.ini
```

- To check that everything is OK, go to <http://localhost:6543/health> in your browser

## Code layout

The API is a [FastAPI](https://fastapi.tiangolo.com/) application, served by gunicorn through PasteDeploy (`c2corg_api:main`, the settings come from the `.ini` file).

- `c2corg_api/app.py`: the FastAPI application, its middlewares (CORS, token validation, unexpected errors) and the answers to unknown routes and methods.
- `c2corg_api/web/`: the routes, one module per resource (`documents.py`, `users.py`, `navitia.py`…). They are thin: each one runs a method of a view class through `web/compat.py`, which gives the views the request they expect (`validated`, `errors`, `matchdict`…) and turns what they return or raise into the answer.
- `c2corg_api/views/`: the view classes and their validators (`views/validation.py`). `@view(...)` in `views/resource.py` declares the validators, permission and content type of a method; the route checks the rate limiting (writes only), then the content type, the permission and the validators, and calls the method.
- `c2corg_api/schemas/`: the Pydantic schemas of the request bodies; `c2corg_api/models/`: the SQLAlchemy models.
- `c2corg_api/security/`: tokens (`roles.py`), rate limiting, Discourse client; `c2corg_api/httpexceptions.py`: the HTTP errors the views raise.
- `c2corg_api/scripts/`: the Elasticsearch syncer, the job scheduler and the maintenance scripts; they read the `.ini` file with `c2corg_api/config.py`.

## Running tests

- Update the test.ini file:

```shell
# Linux or WSL
./scripts/env_replace config/env.default config/env.dev config/env.local < test.ini.in > test.ini
# Or Windows Powershell
Get-Content test.ini.in | cmd /c "python .\scripts\env_replace config/env.default config/env.dev config/env.local > test.ini"

```

- To run tests , you can either run them directly with pytest (Again, it looks like some tests will not pass in Windows):

```shell
pytest
```

- Or directly in your favorite development IDE (pycharm, vscode...)

### API contract tests

`c2corg_api/tests/contract/` checks what the clients of the API rely on, so that a change of framework or library cannot change it unnoticed:

- `routes.txt` lists every route with its methods and permission. After adding, removing or changing a route, regenerate it with `python -m c2corg_api.tests.contract.inventory`.
- Each contract test sends a request and compares the status, the headers clients rely on (CORS, `Cache-Control`, `ETag`…) and the shape of the JSON body (keys and value types) with a snapshot in `snapshots/`. After an intended change of the API, rewrite the snapshots with `CONTRACT_UPDATE=1 pytest c2corg_api/tests/contract` and review their diff.
- Every route has a contract test (marked with `@contract(...)`); `pending.txt`, empty, would list a route without one. A new route needs its contract test.

### Load test

`scripts/loadtest.py` replays a mix of read requests (documents, listings, search, history) with a few threads and prints throughput and latency percentiles per kind of request. It compares two versions of the API on the same machine and data; run each version twice to see the noise:

```shell
python scripts/loadtest.py http://localhost:6543 --threads 8 --duration 60
```

## Linting

- Format the code and run the linter (CI checks both; in the devcontainer, VS Code formats on save):

```shell
make format   # ruff format + ruff check --fix (also sorts imports)
make lint     # ruff check + ruff format --check
```

- Check the locked dependencies for known vulnerabilities (CI runs it too). Advisories that can't be fixed yet are listed in `AUDIT_IGNORE` in the Makefile, each with its reason:

```shell
make audit    # uv audit
```

- A git pre-commit hook runs ruff before each commit. `make install` and the devcontainer install it; otherwise run once per clone:

```shell
uv run pre-commit install
```

## Other

- Flush redis cache:

 ```shell
python c2corg_api/scripts/redis-flushdb.py development.ini
```
