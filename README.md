# [camptocamp.org](https://www.camptocamp.org) API

[![GitHub license](https://img.shields.io/github/license/c2corg/v6_api.svg)](https://github.com/c2corg/v6_api/blob/master/LICENSE)
![Build status](https://github.com/c2corg/v6_api/actions/workflows/ci.yml/badge.svg)
![Github Code scanning](https://github.com/c2corg/v6_api/workflows/Github%20Code%20scanning/badge.svg?branch=master)
[![Codacy Badge](https://app.codacy.com/project/badge/Coverage/323754cf688042688899e6028fdfeff7)](https://www.codacy.com/gh/c2corg/v6_api/dashboard?utm_source=github.com&utm_medium=referral&utm_content=c2corg/v6_api&utm_campaign=Badge_Coverage)
[![Total alerts](https://img.shields.io/lgtm/alerts/g/c2corg/v6_api.svg?logo=lgtm&logoWidth=18)](https://lgtm.com/projects/g/c2corg/v6_api/alerts/)
[![Known Vulnerabilities](https://snyk.io/test/github/c2corg/v6_api/badge.svg)](https://snyk.io/test/github/c2corg/v6_api)

## Development environment

On any OS, install [git](https://git-scm.com/) and [docker](https://docs.docker.com/install/). Then :

### Install

```sh
# Download camptocamp.org source code :
git clone https://github.com/c2corg/v6_api
cd v6_api
```

### Run

```sh
# the very first call may be quite long, (15 minutes, depending of your bandwith)
# time to make a coffee
docker-compose up
```

:heart: <http://localhost:6543> :heart:

Press CTRL+C to terminate it.

### Run the background jobs and syncer scripts

In distinct terminals:

```sh
docker-compose exec api make -f config/docker-dev run-background-jobs
docker-compose exec api make -f config/docker-dev run-syncer
```

### Check code quality

In another terminal (`docker-compose up` must be running) :

```sh
./scripts/lint.sh
```

### Run test suite

In another terminal (`docker-compose up` must be running) :

```sh
# full tests, take a while
./scripts/test.sh

# If you need to test a specific point: 
./scripts/test.sh c2corg_api/tests/models/test_book.py

# or:
./scripts/test.sh c2corg_api/tests/models/test_book.py::TestBook

# or even:
./scripts/test.sh c2corg_api/tests/models/test_book.py::TestBook::test_to_archive
```

Note: if you're using MinGW on Windows, be sure to prefix the command with `MSYS_NO_PATHCONV=1`

## Useful links in [wiki](https://github.com/c2corg/v6_api/wiki)

[Full info about development environment](https://github.com/c2corg/v6_api/wiki/Development-environment-on-Linux)
