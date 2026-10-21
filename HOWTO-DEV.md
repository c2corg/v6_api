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
- [uv](https://docs.astral.sh/uv/getting-started/installation/), which installs the right Python version (3.14) and all dependencies for you
- A docker environment with docker compose plugin (either [docker desktop](https://www.docker.com/products/docker-desktop/) or a manual installation)
- A development IDE is not mandatory, but highly recommended (pycharm, vscode...)
- If you have GNU make installed, you can use it to run all the commands below to initialize and run your development environment (run `make help` to see what can be done) instead of running them "by hand"

### Installing the development environment

- Clone the git repository
- Cd inside your cloned repo
- Install Python and the dependencies (pinned in `uv.lock`) in a `.venv` virtual environment:

```shell
uv sync
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
pserve development.ini --reload
```

- Run background jobs (run each of these commands in a separate terminal, as they will not exit):

```shell
python c2corg_api/scripts/es/syncer.py development.ini
# Does not work in Windows, as it uses signal.pause() which is only available in unix based OSes (Did I already tell you that you should really look at WSL ?)
python c2corg_api/scripts/jobs/scheduler.py development.ini
```

- To check that everything is OK, go to <http://localhost:6543/health> in your browser

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

## Linting

- Run the linter:

```shell
ruff check c2corg_api es_migration
```

## Public transport (GTFS)

The lines and stops shown on the maps come from open GTFS feeds, listed in
`c2corg_api/transport/feeds.json` (id, name, stable download URL, license,
attribution). Adding a network is adding an entry.

- Import the feeds (the ones that did not change since the last import are
  skipped; `--feed <id>` imports only this feed, and can be repeated, `--force`
  imports it anyway):

```shell
import_gtfs development.ini [--feed giffre] [--force]
```

Ids of the feeds to start with (`feeds.json` has more: the other departments,
the other ski resorts and the school lines are left out on purpose). The lines
of a feed without paths (`shapes.txt`) are not drawn, its stops and timetables
are shown anyway.

| Region | Ids |
| --- | --- |
| Auvergne-Rhône-Alpes | `isere`, `savoie`, `haute-savoie`, `drome`, `ardeche`, `cars-region-express`, `chamonix`, `sibra`, `tag`, `synchro` |
| Provence-Alpes-Côte d'Azur | `zou-express`, `zou-proximite`, `zou-trains`, `altigo`, `queyras`, `ecrins` |
| Nouvelle-Aquitaine (Pyrénées) | `pyrenees-atlantiques`, `txik-txak`, `idelis`, `oloron` |
| Occitanie (Pyrénées) | `lio-occitanie`, `tlp`, `arrens-marsous`, `bagneres-la-mongie` |
| Switzerland | none: see below |

```shell
import_gtfs development.ini --feed isere --feed savoie --feed haute-savoie
```

Notes:

- `lio-occitanie`, `puy-de-dome`, `drome` and `ardeche` are the largest feeds
  (18 to 26 MB zipped): the import reads the whole timetable of a feed in
  memory, plan a few GB for them, and import the feeds one at a time with
  `--feed` on a small machine.
- `cars-region-express` and the departments overlap on some stops: a stop can
  be drawn twice.
- The ski resorts shuttles (`courchevel-*`, `belleville`, `val-d-isere`...)
  only run in season: their timetables are empty out of it.
- Switzerland is not importable yet: the national GTFS feed
  (opentransportdata.swiss, updated twice a week, the download link changes
  with each release) has no `shapes.txt`, it is about 120 MB zipped, and it
  needs an importer that does not keep a whole feed in memory.

The same import runs every month (the 1st, at 3:00) in the background jobs
(`python c2corg_api/scripts/jobs/scheduler.py development.ini`).

- The Navitia stops (`guidebook.stopareas`, filled by
  `scripts/public_transport/get_public_transports.sh`) are linked to the GTFS
  stops after each GTFS import and at the end of the Navitia import script
  (`c2corg_api/transport/link_stops.sql`): a stop of a waypoint then shows the
  timetables of its lines. To link them by hand:

```shell
psql -v max_distance=50 -f c2corg_api/transport/link_stops.sql
```

### Duplicate stops and lines

The same stop or line is often in several feeds (a regional express coach and
the network of a department, a train and a regional feed...), with other ids and
other names. Once the feeds are imported, `import_gtfs` groups the stops of the
same place and hides the lines that are in several feeds (nothing is deleted):

- **stops**: `transport_stops.cluster_id` is the id of the main stop of the
  place (the one with the most departures; itself for a stop alone). On the
  map a place is one stop, and its modal gives the timetables of all its feeds.
  A stop joins the main stop if it is at less than 15 m, whatever its name, or
  at less than 50 m with a name that looks like it (one contains the other, or
  half of the words are the same) or a line with the same code. It never
  follows a street from one stop to the next.
- **lines**: `transport_lines.duplicate_of` is the line a hidden line is a
  duplicate of. Two lines of two feeds with the same mode and code are
  duplicates if each path is covered at 90% by the other one, within 25 m (a
  short line in a long one is not a duplicate). The line with the most trips is
  kept; a hidden line still gives the kept line on `/transport-lines/{id}`.

The thresholds are the constants of `c2corg_api/transport/dedup.py`.

To do it again, once the imports are done, without importing anything (after
changing the thresholds, after an import of Navitia stops, or if a feed was
imported by hand), it links the Navitia stops, groups the stops and hides the
lines again in one transaction:

```shell
transport_postprocess development.ini
```

With `--report`, it writes the groups of stops with different names (the main
stop, then the stops of its group with their distance) and the hidden lines
(with the line they duplicate): read them to check the thresholds, on an
area where several feeds overlap (for example Isère and Cars Région Express).

```shell
transport_postprocess development.ini --report
```

The same thing is done by `import_gtfs`, the next time it imports a feed. The
Navitia import script only links the Navitia stops, it does not need more.

## Other

- Flush redis cache:

 ```shell
python c2corg_api/scripts/redis-flushdb.py development.ini
```
