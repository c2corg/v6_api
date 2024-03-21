TEMPLATE_FILES_IN = $(filter-out ./.build/% ./apache/%, $(shell find . -type f -name '*.in'))
TEMPLATE_FILES = $(TEMPLATE_FILES_IN:.in=)

ENV_FILES = config/env.default config/env.dev

ifdef CONFIG
	ENV_FILES += $(CONFIG)
endif

ifneq ($(wildcard config/env.local),)
	ENV_FILES += config/env.local
endif

SRC_DIRS = c2corg_api es_migration

DOCKER_COMPOSE = docker compose
DOCKER_EXEC = $(DOCKER_COMPOSE) exec

ifdef DETACHED
	API_EXEC=$(DOCKER_EXEC) -d api
else
	API_EXEC=$(DOCKER_EXEC) api
endif

DB_EXEC = $(DOCKER_EXEC) -u postgres -T postgresql

PYTHON = $(API_EXEC) python
PYTHON_BG = $(API_EXEC_BG) python

PYTEST = $(API_EXEC) pytest
FLAKE = $(API_EXEC) flake8
PIP = $(API_EXEC) pip
PY3COMPILE = $(API_EXEC) py3compile

help:
	@echo "Usage: make <target>"
	@echo
	@echo "Main targets:"
	@echo
	@echo "- bootstrap"				Bootstraps the project for the first time
	@echo "- run-syncer				Run the ElasticSearch syncer script."
	@echo "- run-background-jobs"	Run the background jobs
	@echo
	@echo "- test					Run the unit tests"
	@echo "- lint					Run flake8 checker on the Python code"
	@echo
	@echo "Secondary targets:"
	@echo
	@echo "- start"					Start the docker containers
	@echo "- stop"					Stop the docker containers
	@echo "- serve"					Start the Python webserver
	@echo
	@echo "- init-database" 		Initialize the dev database
	@echo "- init-test-database" 	Initialize the test database
	@echo "- init-elastic"			Initialize the elasticsearch index
	@echo "- flush-redis			Clear the Redis cache"
	@echo
	@echo "- install				Install the project dependencies"
	@echo "- loadenv				Replace the env vars in the .in templates"
	@echo "- upgrade				Upgrade the dependencies."
	@echo "- upgrade-dev			Upgrade the dev. dependencies."


bootstrap:
		$(MAKE) start
		$(MAKE) install
		$(MAKE) load-env
		$(MAKE) DETACHED=true serve
		$(MAKE) init-database
		$(MAKE) init-elastic
		$(MAKE) DETACHED=true run-syncer
		$(MAKE) DETACHED=true run-background-jobs

start:
		$(DOCKER_COMPOSE) up -d

stop:
		$(DOCKER_COMPOSE) stop

serve:
		$(API_EXEC) pserve development.ini --reload

lint: 
		$(FLAKE) $(SRC_DIRS)
		@echo "Wonderful, python style is Ok!"

test:
		$(MAKE) init-test-database
		$(PYTEST) --cov=c2corg_api

init-database:
		$(DB_EXEC) /v6_api/scripts/database/create_schema.sh
		$(API_EXEC) initialize_c2corg_api_db development.ini

init-test-database:
		$(DB_EXEC) /v6_api/scripts/database/create_test_schema.sh

init-elastic:
		$(API_EXEC) fill_es_index development.ini

install:
		$(PIP) install -r dev-requirements.txt
		$(PIP) install -r requirements.txt
		$(PY3COMPILE) -f .build/venv/

upgrade:
		$(PIP) install install --upgrade -r requirements.txt

upgrade-dev:
		$(PIP) install --upgrade -r dev-requirements.txt


run-syncer:
		$(PYTHON) c2corg_api/scripts/es/syncer.py development.ini

run-background-jobs: 
		$(PYTHON) c2corg_api/scripts/jobs/scheduler.py development.ini

flush-redis: 
		$(PYTHON) c2corg_api/scripts/redis-flushdb.py development.ini

load-env: $(TEMPLATE_FILES)

development.ini: common.ini

.PHONY: $(TEMPLATE_FILES)
$(TEMPLATE_FILES): %: %.in
		$(API_EXEC) scripts/env_replace ${ENV_FILES} < $< > $@
