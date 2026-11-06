"""Fixtures of the contract tests."""

import pytest

from c2corg_api.tests.contract import Browser
from c2corg_api.tests.contract.documents import Documents, create_documents


@pytest.fixture
def browser(client, settings):
    """Send requests as a browser client does."""
    return Browser(client, settings)


@pytest.fixture
def documents(browser, user_ids) -> Documents:
    """Create one document of each type through the API."""
    return create_documents(browser, user_ids)
