"""
Pytest conftest for c2corg_api tests.

Mocks external HTTP calls to the Navitia API so that tests never depend on
real network access or valid SSL certificates.  All other HTTP requests are
left untouched.
"""

import os
from unittest.mock import MagicMock, patch

import pytest
import requests as _real_requests

os.environ.setdefault('NAVITIA_API_KEY', 'test-key')

NAVITIA_HOST = 'api.navitia.io'


def _selective_get(url, *args, **kwargs):
    """Intercept requests.get: return a fake empty response for Navitia
    URLs and fall through to the real implementation for everything else."""
    if NAVITIA_HOST in str(url):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {}
        return mock_resp
    return _real_requests.get(url, *args, **kwargs)


@pytest.fixture(scope='session', autouse=True)
def test_database():
    """Set up the test database and ElasticSearch index once per test run."""
    # This runs before the first test (it used to happen as a side effect
    # of importing ``c2corg_api.tests``).
    # Like before, nothing is torn down at the end, so the test database can
    # be inspected after a run; the next run starts by resetting it.
    from c2corg_api.tests import setup_package

    setup_package()
    yield


@pytest.fixture(scope='session')
def db_engine():
    """Create the SQLAlchemy engine shared by the whole test run."""
    from c2corg_api.tests import get_engine

    return get_engine()


@pytest.fixture
def db_connection(test_database, db_engine):
    """Open a connection in a transaction rolled back after the test."""
    # Tests never see each other's changes: everything, including commit()
    # calls, happens inside this transaction. DBSession, the scoped session
    # used by the views, is bound to it.
    from c2corg_api.models import DBSession
    from c2corg_api.tests import keep

    connection = db_engine.connect()
    trans = connection.begin()
    DBSession.configure(bind=connection)
    yield connection
    if keep:
        trans.commit()
    elif trans.is_active:
        # the code under test may already have rolled it back
        trans.rollback()
    DBSession.remove()
    connection.close()


@pytest.fixture(scope='class')
def wsgi_app(test_database):
    """Build the API's WSGI application, once per test class."""
    from c2corg_api import main
    from c2corg_api.tests import settings

    return main({}, **settings)


@pytest.fixture
def client(wsgi_app):
    """Return the HTTP client the tests use to call the API."""
    # Today a WebTest TestApp around the Pyramid application. This is the
    # single place to swap in another client (e.g. an adapter over FastAPI's
    # TestClient with the same interface) when the web framework changes.
    from webtest import TestApp

    return TestApp(wsgi_app)


@pytest.fixture(autouse=True)
def mock_navitia_requests():
    """Automatically mock ``requests.get`` calls targeting the Navitia API
    (``api.navitia.io``) so that the ``process_new_waypoint`` SQLAlchemy
    event listener never hits the real endpoint.  Non-Navitia requests are
    forwarded to the real ``requests.get``."""
    with patch('c2corg_api.requests.get', side_effect=_selective_get):
        yield
