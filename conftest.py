"""Root conftest, loaded by pytest before the c2corg_api.tests package."""

import pytest

# pytest only rewrites `assert` in test modules and conftest files. The
# shared helpers live in the c2corg_api.tests package modules: register
# them before they are imported, so their failing asserts show the values.
pytest.register_assert_rewrite('c2corg_api.tests')
