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

# Override for rootless Podman: make DOCKER_COMPOSE="podman compose" <target> (or export DOCKER_COMPOSE)
DOCKER_COMPOSE ?= docker compose
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

# --wait: until the healthchecks pass, i.e. the dev database is restored (first start) and Elasticsearch is up
start:
		$(DOCKER_COMPOSE) up -d --wait

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

# The image ghcr.io/c2corg/c2corg-dev-db (docker-compose.yml) comes with the anonymized dev database already
# restored: it is only migrated to the alembic revision of the checkout. An empty server gets the empty schema
# instead (initialize_c2corg_api_db is not idempotent: it is only run on a fresh database).
init-database:
		@if $(DB_EXEC) psql -d c2corg -tAc 'SELECT 1 FROM alembic.alembic_version' > /dev/null 2>&1; then \
			echo "Dev database already initialized, migrating it to the latest revision"; \
			$(UV_RUN) alembic upgrade head; \
		else \
			$(DB_EXEC) /v6_api/scripts/database/create_schema.sh && \
			$(UV_RUN) initialize_c2corg_api_db development.ini; \
		fi

init-test-database:
		$(DB_EXEC) /v6_api/scripts/database/create_test_schema.sh

# Same logic as .devcontainer/setup.sh: create the index with its mappings (without them the search silently
# finds nothing), keep the index of the image ghcr.io/c2corg/c2corg-dev-es if it was built by the indexing code
# of this checkout, otherwise rebuild it from the database (about 5 minutes).
ES_INDEX_URL = http://localhost:9200/c2corg
init-elastic:
		$(UV_RUN) initialize_c2corg_api_es development.ini
		@count=$$(curl -s "$(ES_INDEX_URL)/_count" | sed -n 's/.*"count":\([0-9]*\).*/\1/p'); \
		if [ "$${count:-0}" -gt 0 ] && $(UV_RUN) es_index_fingerprint check development.ini; then \
			echo "The index contains $$count documents and is up to date"; \
		else \
			echo "Rebuilding the index with the current indexing code"; \
			curl -s -X DELETE "$(ES_INDEX_URL)" > /dev/null; \
			$(UV_RUN) initialize_c2corg_api_es development.ini && \
			$(UV_RUN) fill_es_index development.ini && \
			$(UV_RUN) es_index_fingerprint store development.ini; \
		fi

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
