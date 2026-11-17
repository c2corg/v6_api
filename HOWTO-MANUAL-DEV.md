# Manual development setup (Python on the host)

> [!WARNING]
> **Not the recommended setup.** Use the [Dev Container](README.md#getting-started-dev-container-recommended)
> unless you need Python on your host (e.g. an IDE or debugger that cannot work in a container).
> Here you install and maintain Python 3.15 and the dependencies yourself, and this setup is less tested.

> [!WARNING]
> **Do not mix it with the Dev Container in the same checkout.**
> - Both generate the same `*.ini` files, with different service hostnames (`localhost` here, the
>   container names there). After switching, regenerate them: `make load-env` here,
>   `bash .devcontainer/setup.sh` in the dev container.
> - They use different Compose files and volumes (`docker-compose.yml` here,
>   `.devcontainer/docker-compose.yml` there): their databases are separate, so do not run both stacks.
> - The root `docker-compose.yml` publishes PostgreSQL, Elasticsearch and Redis on
>   `127.0.0.1:5432`, `:9200` and `:6379`: stop any local service using these ports.

Only the setup differs: the configuration, the data, running the API, the tests and the linting are
described in the [README](README.md#configuration-and-development-data), and the commands work the
same here, run **on your host**.

## Requirements

- Linux, macOS, or Windows with [WSL](https://learn.microsoft.com/windows/wsl/install) (native Windows is not supported).
- [uv](https://docs.astral.sh/uv/getting-started/installation/) 0.13 or newer: it installs Python 3.15 and the locked dependencies.
- Docker with Compose v2, or Podman (see [Podman](README.md#podman)).
- GNU make (`make help` lists the targets).

## Setting up

```sh
git clone https://github.com/c2corg/v6_api && cd v6_api
cp config/env.local.sample config/env.local   # points the configuration to localhost
make bootstrap                                # with Podman: export DOCKER_COMPOSE="podman compose" first
make serve                                    # then http://localhost:6543/health
```

`make bootstrap` starts the services of `docker-compose.yml` and waits for them to be healthy
(`make start`), installs the dependencies in `.venv` and the git pre-commit hook (`make install`),
generates the `*.ini` files (`make load-env`), migrates the dev database (`make init-database`),
creates the test database (`make init-test-database`) and checks or rebuilds the search index
(`make init-elastic`). Each step can be re-run on its own.

The `make` targets run Python with `uv run`. For the other Python commands of the README
(`pytest`, `alembic`…), prefix them with `uv run` or activate the virtual environment first:
`source .venv/bin/activate`.

## Day to day

```sh
make start   # start the services (they keep their data)
make serve   # plus make run-syncer and make run-background-jobs, one terminal each
make stop    # stop the services
```

After pulling or switching branches: `make install load-env init-database init-elastic`.

## Resetting the data

To start again from a fresh database and index (**deletes your local data**):

```sh
docker compose down -v   # removes the volumes postgres18_data and es_data
docker compose pull
make bootstrap
```

The volume `postgres_data` of the former setup (PostGIS 16 and the 2018 Elasticsearch image) is no
longer used and can be removed.
