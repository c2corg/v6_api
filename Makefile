# Only the tracked templates: a find would also walk into .venv and into the
# git worktrees under .claude/worktrees, and overwrite their config files.
TEMPLATE_FILES_IN = $(filter-out MANIFEST.in, $(shell git ls-files '*.in'))
TEMPLATE_FILES = $(TEMPLATE_FILES_IN:.in=)

ENV_FILES = config/env.default config/env.dev

ifneq ($(wildcard config/env.local),)
	ENV_FILES += config/env.local
endif

# Last, so that it wins over env.local (e.g. the container hostnames of the dev container)
ifdef CONFIG
	ENV_FILES += $(CONFIG)
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

# Known vulnerabilities that cannot be fixed yet, as `PYSEC-...` ids. Re-check each
# one when the reason goes away.
AUDIT_IGNORE =

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
# finds nothing), keep the indices (one per document type, c2corg_<type>) already in the Elasticsearch volume if
# they were built by the indexing code of this checkout, otherwise rebuild them from the database (about 5 minutes).
# ES_INDEX_URL is the URL of the index prefix.
ES_INDEX_URL ?= http://localhost:9200/c2corg
init-elastic:
		$(UV_RUN) initialize_c2corg_api_es development.ini
		@set -e; \
		count=$$(curl -sS "$(ES_INDEX_URL)_*/_count" | sed -n 's/.*"count":\([0-9]*\).*/\1/p'); \
		if [ "$${count:-0}" -gt 0 ] && $(UV_RUN) es_index_fingerprint check development.ini; then \
			echo "The index contains $$count documents and is up to date"; \
		else \
			echo "Rebuilding the index with the current indexing code"; \
			for doc_type in a b c i m o r u w x; do \
				curl -sS -X DELETE "$(ES_INDEX_URL)_$$doc_type" > /dev/null; \
			done; \
			$(UV_RUN) initialize_c2corg_api_es development.ini; \
			for attempt in 1 2 3; do \
				$(UV_RUN) fill_es_index development.ini && break; \
				if [ "$$attempt" = 3 ]; then \
					echo "fill_es_index failed 3 times" >&2; exit 1; \
				fi; \
				echo "fill_es_index failed (attempt $$attempt), retrying in 10s..." >&2; \
				sleep 10; \
			done; \
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
