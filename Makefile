# Only the tracked templates: a find would also walk into .venv and into the
# git worktrees under .claude/worktrees, and overwrite their config files.
TEMPLATE_FILES_IN = $(filter-out MANIFEST.in, $(shell git ls-files '*.in'))
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

# Run the Python tools from the project venv, no need to activate it
UV_RUN = uv run --frozen

.PHONY: help
help:
	@echo "Usage: make <target>"
	@echo
	@echo "Main targets:"
	@echo
	@echo "  bootstrap            Bootstrap the project for the first time"
	@echo "  run-syncer           Run the ElasticSearch syncer script"
	@echo "  run-background-jobs  Run the background jobs"
	@echo
	@echo "  test                 Run the unit tests"
	@echo "  format               Format the Python code with ruff (and apply safe lint fixes)"
	@echo "  lint                 Check the Python code with ruff (lint and formatting)"
	@echo "  audit                Check the locked dependencies for known vulnerabilities"
	@echo
	@echo "Secondary targets:"
	@echo
	@echo "  start                Start the docker containers"
	@echo "  stop                 Stop the docker containers"
	@echo "  serve                Start the Python webserver"
	@echo
	@echo "  init-database        Initialize the dev database"
	@echo "  init-test-database   Initialize the test database"
	@echo "  init-elastic         Initialize the elasticsearch index"
	@echo "  flush-redis          Clear the Redis cache"
	@echo
	@echo "  install              Install the project dependencies and the git pre-commit hook"
	@echo "  load-env             Replace the env vars in the .in templates"
	@echo "                       (make CONFIG=<env file> load-env adds an env file)"

.PHONY: bootstrap start stop serve lint test init-database init-test-database \
		init-elastic install run-syncer run-background-jobs flush-redis load-env

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
		C2C_API_CONFIG=development.ini $(UV_RUN) uvicorn c2corg_api.asgi:app --reload --host 0.0.0.0 --port 6543

.PHONY: format
format:
		$(UV_RUN) ruff format $(SRC_DIRS)
		$(UV_RUN) ruff check --fix $(SRC_DIRS)

lint:
		$(UV_RUN) ruff check $(SRC_DIRS)
		$(UV_RUN) ruff format --check $(SRC_DIRS)
		@echo "Wonderful, python style is Ok!"

# Known vulnerabilities that cannot be fixed yet. Re-check each one when the
# reason goes away:
# - urllib3 1.26: elasticsearch 2.4.1 requires urllib3<2 (goes away with the
#   Elasticsearch 8 migration). The API only talks to trusted hosts with it.
AUDIT_IGNORE = \
		PYSEC-2026-141 PYSEC-2026-1994 PYSEC-2026-1996 PYSEC-2026-1998 \
		PYSEC-2026-1999 PYSEC-2026-4175 PYSEC-2026-4177

.PHONY: audit
audit:
		uv audit --frozen --preview-features audit-command \
			$(foreach id,$(AUDIT_IGNORE),--ignore $(id))

test:
		$(UV_RUN) pytest -n 4

init-database:
		$(DB_EXEC) /v6_api/scripts/database/create_schema.sh
		$(UV_RUN) initialize_c2corg_api_db development.ini

init-test-database:
		$(DB_EXEC) /v6_api/scripts/database/create_test_schema.sh

init-elastic:
		$(UV_RUN) fill_es_index development.ini

install:
		uv sync
		uv run --frozen pre-commit install

run-syncer:
		$(UV_RUN) python c2corg_api/scripts/es/syncer.py development.ini

run-background-jobs:
		$(UV_RUN) python c2corg_api/scripts/jobs/scheduler.py development.ini

flush-redis:
		$(UV_RUN) python c2corg_api/scripts/redis-flushdb.py development.ini

load-env: $(TEMPLATE_FILES)

development.ini: common.ini

.PHONY: $(TEMPLATE_FILES)
$(TEMPLATE_FILES): %: %.in
		$(UV_RUN) scripts/env_replace ${ENV_FILES} < $< > $@
