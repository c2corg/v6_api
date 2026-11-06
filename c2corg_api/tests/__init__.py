import datetime
import logging
import os
import time
from random import randint

import jwt
import pytest
from alembic.command import downgrade
from alembic.config import Config
from dotenv import load_dotenv
from sqlalchemy import create_engine, engine_from_config, text
from sqlalchemy.engine import make_url

from c2corg_api import caching as caching_common
from c2corg_api.config import get_appsettings
from c2corg_api.models import DBSession, commit_or_rollback
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.sso import SsoExternalId, SsoKey
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import UserProfile
from c2corg_api.scripts import initializedb, initializees
from c2corg_api.scripts.es.fill_index import fill_index
from c2corg_api.search import configure_es_from_config
from c2corg_api.security.roles import add_token, create_claims, hash_token

load_dotenv()

log = logging.getLogger(__name__)

curdir = os.path.dirname(os.path.abspath(__file__))
configfile = os.path.realpath(os.path.join(curdir, '../../test.ini'))
settings = get_appsettings(configfile)


def _isolate_worker(settings):
    """Give a pytest-xdist worker its own database, ES index and Redis names."""
    # Each worker is a process of its own: only what lives outside of it is
    # shared. Without a worker (no -n), the settings are used as they are.
    worker = os.environ.get('PYTEST_XDIST_WORKER')
    if not worker:
        return
    url = make_url(settings['sqlalchemy.url'])
    url = url.set(database=f'{url.database}_{worker}')
    settings['sqlalchemy.url'] = url.render_as_string(hide_password=False)
    for key in (
        'elasticsearch.index',
        # also the prefix of the rate limiting counters
        'redis.cache_key_prefix',
        'redis.exchange',
        'redis.queue_es_sync',
    ):
        settings[key] = f'{settings[key]}_{worker}'


_isolate_worker(settings)

alembic_scripts_folder = os.path.realpath(
    os.path.join(curdir, '../../alembic_migration')
)


def errors_of(body):
    """Return the errors of an answer as {location, name, description}."""
    # the envelope of the API (400...), or FastAPI's 422 (#2546): its field
    # as a dotted path, as the envelope named it
    if 'detail' in body:
        return [
            {
                'location': error['loc'][0],
                'name': '.'.join(str(part) for part in error['loc'][1:]),
                'description': error['msg'],
            }
            for error in body['detail']
        ]
    return body['errors']


def assert_required(error, name):
    """Check an error for a missing field."""
    # FastAPI's text in a 422, the API's in its envelope
    assert error.get('description') in ('Field required', 'Required')
    assert error.get('name') == name


def assert_not_in_enum(error, name):
    """Check an error for a value outside of an enumeration."""
    assert 'is not one of' in error.get('description')
    assert error.get('name') == name


def send_json(client, method, *args, status=200, **kwargs):
    """Send a JSON body; fail unless the answer has the given status ('*': any)."""
    kwargs['expect_errors'] = True
    res = getattr(client, method + '_json')(*args, **kwargs)
    if status != '*' and res.status_code != status:
        errors = res.body if res.status_code == 400 else ''
        pytest.fail(f'Bad response: {res.status} (not {status}) : {errors}')
    return res


def auth_headers(username=None, token=None, headers=None):
    """Return the headers with the token of the given user (or token)."""
    if not headers:
        headers = {}
    if not token:
        token = global_tokens[username]
    headers['Authorization'] = 'JWT token="' + token + '"'
    return headers


def get_error(errors, name):
    """Return the error about the given name; fail without one."""
    for error in errors:
        if name == error.get('name'):
            return error
    pytest.fail(f'no error for {name}')


def get_locale(locales, lang):
    """Return the locale of the given language in a JSON list of locales."""
    return next(filter(lambda locale: locale['lang'] == lang, locales), None)


def assert_errors_contain(body, key, value=None):
    """Check that an answer has an error about `key` (with this description)."""
    for error in errors_of(body):
        if error.get('name') == key:
            if value is not None:
                assert error.get('description') == value
            return
    pytest.fail(str(body) + ' does not contain ' + key)


def assert_body_equal(body, key, expected):
    """Check a value of a JSON body."""
    assert body.get(key) == expected


def assert_error(errors, name, description):
    """Check that the errors include this one."""
    for error in errors:
        if description == error.get('description') and name == error.get('name'):
            return
    pytest.fail(f'no error ({name}, {description}) in {errors}')


def assert_coordinates_equal(coord1, coord2):
    """Check two coordinates, to the nearest 5e-8."""
    assert len(coord1) == len(coord2), 'not the same dimension'
    for i in range(0, len(coord1)):
        assert coord1[i] == pytest.approx(coord2[i], abs=5e-8), (
            f'{coord1[i]} does not almost equal {coord2[i]}'
        )


def get_json_with_token(client, url, token, status=200):
    """GET a URL with the given token; return the JSON body."""
    headers = auth_headers(token=token)
    return client.get(url, headers=headers, status=status).json


def get_json_with_contributor(client, url, status=200):
    """GET a URL as the contributor; return the JSON body."""
    headers = auth_headers(username='contributor')
    return client.get(url, headers=headers, status=status).json


def get_json_with_moderator(client, url, status):
    """GET a URL as the moderator; return the JSON body."""
    headers = auth_headers(username='moderator')
    return client.get(url, headers=headers, status=status).json


def post_json_with_token(client, url, token, body={}, status=200):
    """POST a JSON body with the given token; return the JSON answer."""
    headers = auth_headers(token=token)
    return send_json(client, 'post', url, body, headers=headers, status=status).json


def post_json_with_contributor(
    client, url, body={}, status=200, username='contributor', headers={}
):
    """POST a JSON body as a user (the contributor); return the JSON answer."""
    headers = auth_headers(username=username, headers=headers)
    return send_json(client, 'post', url, body, headers=headers, status=status).json


def assert_notified_es(queue_config):
    """Check that a sync. notification was sent for ES, and take it."""
    queue = queue_config.queue(queue_config.connection)
    assert queue.get() is not None, 'no sync. notification sent for ES'


def assert_not_notified_es(queue_config):
    """Check that no sync. notification was sent for ES."""
    queue = queue_config.queue(queue_config.connection)
    assert queue.get() is None, 'unexpected sync. notification sent for ES'


def sync_es_queue(session, queue_config):
    """Check the sync. notification for ES, then sync. the index."""
    from c2corg_api.scripts.es.sync import sync_es

    assert_notified_es(queue_config)
    sync_es(session)


def get_feed_change(session, document_id, change_type=None):
    """Return the feed entry of a document (of the given type of change)."""
    from c2corg_api.models.feed import DocumentChange

    q = session.query(DocumentChange).filter(DocumentChange.document_id == document_id)
    if change_type:
        q = q.filter(DocumentChange.change_type == change_type)
    return q.first()


def invalid_parameters(response):
    """Return the (location, name, message) of the errors of a 422 answer."""
    # FastAPI's validation errors: `loc` is the location and the name
    return [(*error['loc'], error['msg']) for error in response.json['detail']]


def get_engine():
    return engine_from_config(settings, 'sqlalchemy.')


def _get_alembic_config():
    alembic_config = Config()
    alembic_config.set_main_option('script_location', alembic_scripts_folder)
    alembic_config.set_main_option('sqlalchemy.url', settings['sqlalchemy.url'])
    alembic_config.set_main_option('version_table_schema', 'alembic')
    return alembic_config


global_userids = {}
global_tokens = {}
global_passwords = {}


def _add_global_test_data(session):
    global_passwords['contributor'] = 'super pass'
    global_passwords['contributor2'] = 'better pass'
    global_passwords['moderator'] = 'even better pass'
    global_passwords['robot'] = 'bombproof pass'

    contributor_profile = UserProfile(
        categories=['amateur'],
        locales=[
            DocumentLocale(title='', description='Me', lang='en'),
            DocumentLocale(title='', description='Moi', lang='fr'),
        ],
        geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
    )

    contributor = User(
        name='Contributor',
        username='contributor',
        email='contributor@camptocamp.org',
        forum_username='contributor',
        password='super pass',
        tos_validated=datetime.datetime(2020, 12, 28),
        email_validated=True,
        profile=contributor_profile,
    )

    contributor2_profile = UserProfile(
        categories=['amateur'], locales=[DocumentLocale(title='...', lang='en')]
    )

    contributor2 = User(
        name='Contributor 2',
        username='contributor2',
        email='contributor2@camptocamp.org',
        forum_username='contributor2',
        password='better pass',
        email_validated=True,
        tos_validated=datetime.datetime(2021, 2, 12),
        profile=contributor2_profile,
    )

    contributor3_profile = UserProfile(
        categories=['amateur'], locales=[DocumentLocale(title='...', lang='en')]
    )

    contributor3 = User(
        name='Contributor 3',
        username='contributor3',
        email='contributor3@camptocamp.org',
        forum_username='contributor3',
        password='poor password',
        email_validated=True,
        tos_validated=datetime.datetime(2006, 1, 1),
        profile=contributor3_profile,
    )

    contributor_notos_profile = UserProfile(
        categories=['amateur'], locales=[DocumentLocale(title='...', lang='en')]
    )

    contributor_notos = User(
        name='Contributor no ToS',
        username='contributornotos',
        email='contributornotos@camptocamp.org',
        forum_username='contributornotos',
        password='some password',
        email_validated=True,
        profile=contributor_notos_profile,
    )

    moderator_profile = UserProfile(
        categories=['mountain_guide'], locales=[DocumentLocale(title='', lang='en')]
    )

    moderator = User(
        name='Moderator',
        username='moderator',
        email='moderator@camptocamp.org',
        forum_username='moderator',
        moderator=True,
        password='even better pass',
        tos_validated=datetime.datetime(2021, 2, 12),
        email_validated=True,
        profile=moderator_profile,
    )

    robot_profile = UserProfile(locales=[DocumentLocale(title='', lang='en')])

    robot = User(
        name='Robot',
        username='robot',
        email='robot@camptocamp.org',
        forum_username='robot',
        robot=True,
        password='bombproof pass',
        tos_validated=datetime.datetime(2021, 6, 6),
        email_validated=True,
        profile=robot_profile,
    )

    users = [
        robot,
        moderator,
        contributor,
        contributor2,
        contributor3,
        contributor_notos,
    ]
    session.add_all(users)
    session.flush()

    # like a registration (UserRegistrationRest.post), give the profiles their
    # first version, so that they can be updated
    from c2corg_api.views.document import create_new_version

    for user in users:
        create_new_version(user.profile, user.id)

    domain = 'www.somewhere.com'
    sso_key = SsoKey(domain=domain, key=hash_token(domain))
    session.add(sso_key)

    sso_external_id = SsoExternalId(
        domain=domain,
        external_id='1',
        user=contributor,
        token='token',
        expire=datetime.datetime.now(datetime.UTC),
    )
    session.add(sso_external_id)

    session.flush()

    key = settings['jwt.private_key']
    algorithm = 'HS256'
    now = datetime.datetime.now(datetime.UTC)
    exp = now + datetime.timedelta(weeks=10)

    for user in users:
        claims = create_claims(user, now, exp)
        token = jwt.encode(claims, key=key, algorithm=algorithm)
        add_token(token, exp, user.id)
        global_userids[user.username] = user.id
        global_tokens[user.username] = token


def _create_database():
    """Create the test database if it does not exist yet, as the CI does."""
    # see scripts/database/create_test_schema.sh
    url = make_url(settings['sqlalchemy.url'])
    admin = create_engine(url.set(database='postgres'), isolation_level='AUTOCOMMIT')
    try:
        with admin.connect() as connection:
            exists = connection.execute(
                text('SELECT 1 FROM pg_database WHERE datname = :name'),
                {'name': url.database},
            ).scalar()
            if exists:
                return
            # the name comes from test.ini and the worker id
            connection.execute(text(f'CREATE DATABASE "{url.database}"'))
    finally:
        admin.dispose()

    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.execute(text('CREATE EXTENSION IF NOT EXISTS postgis'))
            for schema in ('guidebook', 'users', 'sympa', 'alembic'):
                connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS {schema}'))
    finally:
        engine.dispose()


def setup_package():
    """Create the test database and ElasticSearch index, once per run."""
    # Called by the session fixture in conftest.py (not at import time, so
    # importing this package has no side effect).
    # set up database
    _create_database()
    engine = get_engine()
    DBSession.configure(bind=engine)

    alembic_config = _get_alembic_config()
    downgrade(alembic_config, 'base')
    initializedb.setup_db(alembic_config, DBSession)

    # set up ElasticSearch
    configure_es_from_config(settings)
    initializees.drop_index()
    initializees.setup_es()

    # Add test data needed for all tests
    with commit_or_rollback(DBSession):
        _add_global_test_data(DBSession)
        fill_index(DBSession)
    DBSession.remove()


# keep the database schema after a test run (useful for debugging)
keep = False


def teardown_package():
    # tear down database
    if not keep:
        alembic_config = _get_alembic_config()
        downgrade(alembic_config, 'base')
        initializees.drop_index()


class AssertionsMixin:
    def assertCoodinateEquals(self, coord1, coord2):  # noqa
        assert_coordinates_equal(coord1, coord2)


class BaseTestCase(AssertionsMixin):
    """The idea for unit tests is, that the database tables
    are created only once per test run and every test case uses a
    transaction which is rolled back at the end. This avoids that
    the database is set up and teared down after each test case.

    See also:
    http://www.sontek.net/blog/2011/12/01/writing_tests_for_pyramid_and_sqlalchemy.html
    """

    @pytest.fixture(autouse=True)
    def _base_fixtures(
        self,
        client,
        db_connection,
        session,
        email_service,
        queue_config,
    ):
        """Expose the pytest fixtures to the tests and run setUp/tearDown."""
        # The fixtures are defined in conftest.py.
        self.global_userids = global_userids
        self.global_tokens = global_tokens
        self.global_passwords = global_passwords
        self.settings = settings
        self.app = client
        self.connection = db_connection
        # the session used in the test code, bound to the test's connection
        # (the views use DBSession, bound to the same connection)
        self.session = session
        self.email_service = email_service
        self.queue_config = queue_config
        # pytest does not call setUp/tearDown on plain classes: the
        # subclasses still define them, so call them here
        self.setUp()
        yield
        self.tearDown()

    def setUp(self):
        """Prepare the test; subclasses override it."""

    def tearDown(self):
        """Clean up after the test; subclasses override it."""

    def app_post_json(self, *args, **kwargs):
        return self.app_send_json('post', *args, **kwargs)

    def app_put_json(self, *args, **kwargs):
        return self.app_send_json('put', *args, **kwargs)

    def app_send_json(self, action, *args, **kwargs):
        return send_json(self.app, action, *args, **kwargs)


def reset_queue(queue_config):
    queue = queue_config.queue(queue_config.connection)
    while queue.get():
        pass


def reset_cache_key():
    cache_version = settings['cache_version']
    caching_common.CACHE_VERSION = (
        f'{cache_version}-{int(time.time())}-{randint(0, 10**9)}'
    )
    caching_common.cache_status = caching_common.CacheStatus()
