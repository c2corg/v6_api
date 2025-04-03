# [camptocamp.org](https://www.camptocamp.org) API developer manual

## Requirements

- A computer running Linux or Windows (on Windows, take a look at [WSL](https://learn.microsoft.com/fr-fr/windows/wsl/install), it will make your developer life easier). Maybe MacOs can work, but it was not tested.
- Python 3.9.x installed with pip and the virtualenv package (currently, it will not work with python 3.10+)
    - On Ubuntu, you can install it from the deadsnakes repository if your embedded python version is too recent (https://askubuntu.com/questions/1318846/how-do-i-install-python-3-9)
    - On Windows, use Microsoft Store to install it (https://apps.microsoft.com/detail/9p7qfqmjrfp7)
- A docker environment with docker compose plugin (either [docker desktop](https://www.docker.com/products/docker-desktop/) or a manual installation)
- A development IDE is not mandatory, but highly recommended (pycharm, vscode...)
- If you have GNU make installed, you can use it to run all the commands below to initialize and run your development environment (run `make help` to see what can be done) instead of running them "by hand"

## Installing the development environment

- Clone the git repository
- Cd inside your cloned repo
- Create a virtual environment in it:
```shell
python3.9 -m venv venv
```
- Activate the virtual environment (⚠️ Do not forget to activate it in all terminal instances you intend to use)
```shell
# Linux (or WSL)
source venv/bin/activate
# Or windows powershell
./venv/bin/Activate.ps1
```
- Install the API and its python dependencies in the virtual environment with the following command:
```shell
pip install -e ".[dev]"
```
- Start the necessary tools (postgres database, redis, and elasticsearch) in docker containers:
```shell
docker compose up -d
```
- Go to the config directory and copy the `env.local.sample` to `env.local`
- You should not need to modify it as it is already filled with the necessary values to be compatible with the docker compose defaults but if necessary you can
- Update the `development.ini` file:
```shell
./scripts/env_replace config/env.default config/env.dev config/env.local < development.ini.in > development.ini
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
python c2corg_api/scripts/jobs/scheduler.py development.ini
```
- To check that everything is OK, go to http://localhost:6543/health in your browser

## Running tests

- Update the test.ini file:
```shell
./scripts/env_replace config/env.default config/env.dev config/env.local < test.ini.in > test.ini
```
- To run tests , you can either run them directly with pytest :
```shell
pytest
```
- Or directly in your favorite development IDE (pycharm, vscode...)

## Linting

- Run the linter:
```shell
flake8 c2corg_api es_migration
```

## Other

- Flush redis cache:
 ```shell
python c2corg_api/scripts/redis-flushdb.py development.ini
```
