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
	@echo "- format				Format the Python code with ruff (and apply safe lint fixes)"
	@echo "- lint					Check the Python code with ruff (lint and formatting)"
	@echo "- audit				Check the locked dependencies for known vulnerabilities"
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
	@echo "- install				Install the project dependencies and the git pre-commit hook"
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

.PHONY: format
format:
		ruff format $(SRC_DIRS)
		ruff check --fix $(SRC_DIRS)

lint:
		ruff check $(SRC_DIRS)
		ruff format --check $(SRC_DIRS)
		@echo "Wonderful, python style is Ok!"

# Known vulnerabilities that cannot be fixed yet. Re-check each one when the
# reason goes away:
# - urllib3 1.26: elasticsearch 2.4.1 requires urllib3<2 (goes away with the
#   Elasticsearch 8 migration). The API only talks to trusted hosts with it.
# - setuptools: held below 81 because Pyramid 1.10 needs pkg_resources (goes
#   away with FastAPI). The issues only affect building sdists on macOS and
#   installing legacy wheels on Windows.
# - virtualenv 21.14.12 (dev only, via pre-commit): the fix (21.14.13,
#   2026-10-22) is inside the 2-week cooldown; bump it after 2026-11-05. The
#   issue needs a crafted `--prompt` passed to the bash activator.
AUDIT_IGNORE = \
		PYSEC-2026-141 PYSEC-2026-1994 PYSEC-2026-1996 PYSEC-2026-1998 \
		PYSEC-2026-1999 PYSEC-2026-4175 PYSEC-2026-4177 \
		PYSEC-2026-3447 GHSA-xmj3-9gf7-h52w \
		GHSA-cx6f-vjhg-g3cc

.PHONY: audit
audit:
		uv audit --frozen --preview-features audit-command \
			$(foreach id,$(AUDIT_IGNORE),--ignore $(id))

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
		uv sync
		uv run --frozen pre-commit install

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
