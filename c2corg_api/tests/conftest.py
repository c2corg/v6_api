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
    # the commits and rollbacks of DBSession act on a SAVEPOINT of this
    # transaction, never on the transaction itself
    DBSession.configure(bind=connection, join_transaction_mode='create_savepoint')
    yield connection
    if keep:
        trans.commit()
    elif trans.is_active:
        # the code under test may already have rolled it back
        trans.rollback()
    DBSession.remove()
    connection.close()


@pytest.fixture(scope='class')
def fastapi_app(test_database):
    """Build the API's application, once per test class."""
    from c2corg_api import create_app
    from c2corg_api.tests import settings

    return create_app(settings)


@pytest.fixture
def client(fastapi_app, db_connection):
    """Return the HTTP client the tests use to call the API."""
    # FastAPI's TestClient, with the interface of WebTest (see client.py).
    # It needs db_connection: the views then work in the test's transaction.
    # The state that outlives a request is reset first: the ES sync queue,
    # the cache key, the feed admin account and the shared email service.
    from c2corg_api.emails.email_service import EmailService
    from c2corg_api.tests import reset_cache_key, reset_queue
    from c2corg_api.tests.client import Client

    with Client(fastapi_app) as client:
        reset_queue(client.registry.queue_config)
        reset_cache_key()
        client.registry.feed_admin_user_account_id = None
        EmailService.instance = None
        yield client


@pytest.fixture
def session(db_connection):
    """Return a session in the test's transaction, as the views' DBSession."""
    from c2corg_api.models import sessionmaker

    session = sessionmaker()(bind=db_connection)
    yield session
    session.close()


@pytest.fixture
def settings():
    """Return the settings of the tests (test.ini)."""
    from c2corg_api.tests import settings

    return settings


@pytest.fixture
def user_ids():
    """Return the ids of the test users, by username."""
    from c2corg_api.tests import global_userids

    return global_userids


@pytest.fixture
def tokens():
    """Return the tokens of the test users, by username."""
    from c2corg_api.tests import global_tokens

    return global_tokens


@pytest.fixture
def passwords():
    """Return the passwords of the test users, by username."""
    from c2corg_api.tests import global_passwords

    return global_passwords


@pytest.fixture
def email_service():
    """Return a new email service."""
    from c2corg_api.emails.email_service import EmailService
    from c2corg_api.tests import settings

    # the shared one is reset by `client`
    return EmailService(settings)


@pytest.fixture
def queue_config(client):
    """Return the ES sync queue configuration (emptied by `client`)."""
    return client.registry.queue_config


@pytest.fixture(autouse=True)
def mock_navitia_requests():
    """Automatically mock ``requests.get`` calls targeting the Navitia API
    (``api.navitia.io``) so that the ``process_new_waypoint`` SQLAlchemy
    event listener never hits the real endpoint.  Non-Navitia requests are
    forwarded to the real ``requests.get``."""
    with patch('c2corg_api.requests.get', side_effect=_selective_get):
        yield


@pytest.fixture(autouse=True)
def reset_discourse_client():
    """Drop the Discourse client a test may have replaced or built."""
    # The client is a module global, created on first use. Tests replace it
    # with mocks, or build it while `DiscourseClient` is patched: without a
    # reset, the next tests in the process would get that mock.
    yield
    from c2corg_api.security.discourse_client import set_discourse_client

    set_discourse_client(None)


@pytest.fixture
def discourse(settings):
    """Fake the Discourse client (up); restore the real one after the test."""
    # the Discourse client is global: without the restore, the fake leaks
    # into the tests that run after this one
    from c2corg_api.tests.forum import FakeDiscourse

    discourse = FakeDiscourse(settings)
    yield discourse
    discourse.restore()
