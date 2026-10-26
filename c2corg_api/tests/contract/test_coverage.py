import importlib
import os
import pkgutil

import c2corg_api.tests.contract as contract_tests
from c2corg_api.tests.contract import COVERED
from c2corg_api.tests.contract.inventory import INVENTORY_FILE

# routes without a contract test yet: this list may only shrink
PENDING_FILE = os.path.join(os.path.dirname(__file__), 'pending.txt')


def _routes(path):
    with open(path) as f:
        return {tuple(line.split()[:2]) for line in f if line.strip()}


class TestContractCoverage:
    def setup_method(self):
        # the contract tests register what they cover when imported
        for module in pkgutil.iter_modules(contract_tests.__path__):
            if module.name.startswith('test_'):
                importlib.import_module(f'{contract_tests.__name__}.{module.name}')
        # (method, path) pairs
        self.routes = _routes(INVENTORY_FILE)
        self.covered = set(COVERED)
        self.pending = _routes(PENDING_FILE)

    def test_covered_routes_exist(self):
        assert self.covered - self.routes == set()

    def test_every_route_is_covered_or_pending(self):
        assert self.routes - self.covered - self.pending == set()

    def test_pending_routes_are_not_covered(self):
        # remove a route from pending.txt once it has a contract test
        assert self.pending & self.covered == set()
        assert self.pending - self.routes == set()
