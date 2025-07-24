SITE_PACKAGES = $(shell .build/venv/bin/python -c "import distutils; print(distutils.sysconfig.get_python_lib())" 2> /dev/null)
TEMPLATE_FILES_IN = $(filter-out ./.build/%, $(shell find . -type f -name '*.in'))
TEMPLATE_FILES = $(TEMPLATE_FILES_IN:.in=)

# variables used in config files (*.in)
export base_dir = $(abspath .)
export site_packages = $(SITE_PACKAGES)

include config/default

.PHONY: help
help:
	@echo "Usage: make <target>"
	@echo
	@echo "Main targets:"
	@echo
	@echo "- check			Perform a number of checks on the code (runs flake 8 and test)"
	@echo "- test			Run the unit tests"
	@echo "- clean			Remove generated files"
	@echo "- cleanall		Remove all the build artefacts"
	@echo "- install		Install and build the project"
	@echo "- serve			Run the development server"
	@echo "- run-syncer		Run the ElasticSearch syncer script."
	@echo "- template		Replace the config vars in the .in templates"
	@echo "- clear-cache		Reset the server cache container"
	@echo "- clear-cache-prod	Reset the server cache container in prod environment"
	@echo
	@echo "Secondary targets:"
	@echo
	@echo "- lint			Run flake8 checker on the Python code"
	@echo "- upgrade		Upgrade the dependencies."
	@echo "- upgrade-dev		Upgrade the dev. dependencies."
	@echo "- publish		Push docker image to dockerhub from travis-ci"

.PHONY: check
check: lint test

.PHONY: clean
clean:
	rm -f .build/dev-requirements.timestamp
	rm -f $(TEMPLATE_FILES)

.PHONY: cleanall
cleanall: clean
	rm -rf .build

.PHONY: test
test: .build/venv/bin/pytest template .build/dev-requirements.timestamp .build/requirements.timestamp
	# All tests must be run with authentication/authorization enabled
	.build/venv/bin/pytest --cov=c2corg_api

.PHONY: lint
lint: .build/venv/bin/flake8
	.build/venv/bin/flake8 c2corg_api es_migration
	@echo "Wonderful, python style is Ok! Here is a beer : 🍺"

.PHONY: install
install: .build/requirements.timestamp .build/dev-requirements.timestamp template

.PHONY: template
template: $(TEMPLATE_FILES)

.PHONY: serve
serve: install development.ini
	echo "#\n# Also remember to start the ElasticSearch syncer script with:\n# make -f ... run-syncer\n#"
	.build/venv/bin/pserve development.ini --reload

.PHONY: run-syncer
run-syncer: install development.ini
	.build/venv/bin/python c2corg_api/scripts/es/syncer.py development.ini

.PHONY: run-syncer-prod
run-syncer-prod: install production.ini
	.build/venv/bin/python c2corg_api/scripts/es/syncer.py production.ini

.PHONY: run-background-jobs
run-background-jobs: install development.ini
	.build/venv/bin/python c2corg_api/scripts/jobs/scheduler.py development.ini

.PHONY: run-background-jobs-prod
run-background-jobs-prod: install production.ini
	.build/venv/bin/python c2corg_api/scripts/jobs/scheduler.py production.ini

.PHONY: clear-cache
clear-cache: install development.ini
	.build/venv/bin/python c2corg_api/scripts/redis-flushdb.py development.ini

.PHONY: clear-cache-prod
clear-cache-prod: install production.ini
	.build/venv/bin/python c2corg_api/scripts/redis-flushdb.py production.ini

.PHONY: upgrade
upgrade: .build/venv/bin/pip
	.build/venv/bin/pip install --upgrade -r requirements.txt

.PHONY: upgrade-dev
upgrade-dev: .build/venv/bin/pip
	.build/venv/bin/pip install --upgrade -r dev-requirements.txt

.build/venv/bin/flake8: .build/dev-requirements.timestamp

.build/venv/bin/pytest: .build/dev-requirements.timestamp

.build/dev-requirements.timestamp: .build/venv/bin/pip dev-requirements.txt
	.build/venv/bin/pip install -r dev-requirements.txt
	touch $@

.build/venv/bin/pip:
	mkdir -p $(dir .build/venv)
	virtualenv -p python3 .build/venv
	.build/venv/bin/pip install --upgrade -r requirements_pip.txt

.build/requirements.timestamp: .build/venv/bin/pip requirements.txt setup.py
	.build/venv/bin/pip -V
	.build/venv/bin/pip install -r requirements.txt
	touch $@

development.ini production.ini: common.ini

apache/app-c2corg_api.wsgi: production.ini

apache/wsgi.conf: apache/app-c2corg_api.wsgi

.PHONY: $(TEMPLATE_FILES)
$(TEMPLATE_FILES): %: %.in
	scripts/env_replace < $< > $@
	chmod --reference $< $@

.PHONY: publish
publish: template
	scripts/travis-build.sh
	scripts/travis-publish.sh
