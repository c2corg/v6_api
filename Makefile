SITE_PACKAGES = $(shell .build/venv/bin/python -c "import distutils; print(distutils.sysconfig.get_python_lib())" 2> /dev/null)
TEMPLATE_FILES_IN = $(filter-out ./.build/%, $(shell find . -type f -name '*.in'))
TEMPLATE_FILES = $(TEMPLATE_FILES_IN:.in=)
CONFIG_MAKEFILE = $(shell find config -type f)

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
	@echo "- serve			Run the development server (pserve)"
	@echo "- template		Replace the config vars in the .in templates"
	@echo
	@echo "Secondary targets:"
	@echo
	@echo "- lint			Run flake8 checker on the Python code"
	@echo "- upgrade		Upgrade the dependencies."
	@echo "- upgrade-dev		Upgrade the dev. dependencies."

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
test: .build/venv/bin/nosetests test.ini
	# All tests must be run with authentication/authorization enabled
	.build/venv/bin/nosetests

.PHONY: lint
lint: .build/venv/bin/flake8
	.build/venv/bin/flake8 c2corg_api

.PHONY: install
install: install-dev-egg template

.PHONY: template
template: $(TEMPLATE_FILES)

.PHONY: install-dev-egg
install-dev-egg: $(SITE_PACKAGES)/c2corg_api.egg-link

.PHONY: serve
serve: install development.ini
	.build/venv/bin/pserve --reload development.ini

.PHONY: upgrade
upgrade:
	.build/venv/bin/pip install --upgrade -r requirements.txt

.PHONY: upgrade-dev
upgrade-dev:
	.build/venv/bin/pip install --upgrade -r dev-requirements.txt

.build/venv/bin/flake8: .build/dev-requirements.timestamp

.build/venv/bin/nosetests: .build/dev-requirements.timestamp

.build/dev-requirements.timestamp: .build/venv dev-requirements.txt
	.build/venv/bin/pip install -r dev-requirements.txt
	touch $@

.build/venv:
	mkdir -p $(dir $@)
	virtualenv --no-site-packages -p python3 $@

$(SITE_PACKAGES)/c2corg_api.egg-link: .build/venv requirements.txt setup.py
	.build/venv/bin/pip install -r requirements.txt

development.ini production.ini: common.ini

apache/app-c2corg_api.wsgi: production.ini

apache/wsgi.conf: apache/app-c2corg_api.wsgi

%: %.in $(CONFIG_MAKEFILE)
	scripts/env_replace < $< > $@
	chmod --reference $< $@
