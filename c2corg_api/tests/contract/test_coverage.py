import importlib
import os
import pkgutil

import pytest

import c2corg_api.tests.contract as contract_tests
from c2corg_api.tests.contract import COVERED
from c2corg_api.tests.contract.inventory import INVENTORY_FILE

# routes without a contract test yet: this list may only shrink
PENDING_FILE = os.path.join(os.path.dirname(__file__), 'pending.txt')


def _routes(path):
    with open(path) as f:
        return {tuple(line.split()[:2]) for line in f if line.strip()}


@pytest.fixture(scope='module')
def covered():
    """Return the routes the contract tests cover, as (method, path) pairs."""
    # the contract tests register what they cover when imported
    for module in pkgutil.iter_modules(contract_tests.__path__):
        if module.name.startswith('test_'):
            importlib.import_module(f'{contract_tests.__name__}.{module.name}')
    return set(COVERED)


@pytest.fixture(scope='module')
def routes():
    """Return the routes of the API, as (method, path) pairs."""
    return _routes(INVENTORY_FILE)


@pytest.fixture(scope='module')
def pending():
    """Return the routes without a contract test yet."""
    return _routes(PENDING_FILE)


def test_covered_routes_exist(covered, routes):
    assert covered - routes == set()


def test_every_route_is_covered_or_pending(covered, routes, pending):
    assert routes - covered - pending == set()


def test_pending_routes_are_not_covered(covered, routes, pending):
    # remove a route from pending.txt once it has a contract test
    assert pending & covered == set()
    assert pending - routes == set()
