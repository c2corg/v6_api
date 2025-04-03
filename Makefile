TEMPLATE_FILES_IN = $(filter-out ./.build/% ./apache/% ./venv/% ./MANIFEST.in, $(shell find . -type f -name '*.in'))
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
DB_EXEC = $(DOCKER_EXEC) -u postgres -T postgresql

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


bootstrap:
		$(MAKE) start
		$(MAKE) install
		$(MAKE) load-env
		$(MAKE) init-database
		$(MAKE) init-test-database
		$(MAKE) init-elastic

start:
		$(DOCKER_COMPOSE) up -d

stop:
		$(DOCKER_COMPOSE) stop

serve:
		pserve development.ini --reload

lint: 
		flake8 $(SRC_DIRS)
		@echo "Wonderful, python style is Ok!"

test:
		pytest

init-database:
		$(DB_EXEC) /v6_api/scripts/database/create_schema.sh
		initialize_c2corg_api_db development.ini

init-test-database:
		$(DB_EXEC) /v6_api/scripts/database/create_test_schema.sh

init-elastic:
		fill_es_index development.ini

install:
		pip install -e ".[dev]"

run-syncer:
		python c2corg_api/scripts/es/syncer.py development.ini

run-background-jobs: 
		python c2corg_api/scripts/jobs/scheduler.py development.ini

flush-redis: 
		python c2corg_api/scripts/redis-flushdb.py development.ini

load-env: $(TEMPLATE_FILES)

development.ini: common.ini

.PHONY: $(TEMPLATE_FILES)
$(TEMPLATE_FILES): %: %.in
		scripts/env_replace ${ENV_FILES} < $< > $@
