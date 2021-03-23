import time

import jwt
import datetime
from pytz import utc

import transaction
import os
import logging
from random import randint

from alembic.command import downgrade
from c2corg_api.models.document import DocumentLocale, DocumentGeometry
from c2corg_api.models.user_profile import UserProfile
from c2corg_api.scripts.es.fill_index import fill_index
from sqlalchemy import engine_from_config
from pyramid.paster import get_appsettings
from pyramid import testing
from alembic.config import Config

import unittest
from webtest import TestApp

from c2corg_api.emails.email_service import EmailService

from c2corg_api import main, caching
from c2corg_api import caching as caching_common
from c2corg_api.models import DBSession, sessionmaker
from c2corg_api.models.sso import SsoExternalId, SsoKey
from c2corg_api.models.user import User
from c2corg_api.security.roles import create_claims, add_or_retrieve_token
from c2corg_api.scripts import initializedb, initializees
from c2corg_api.search import configure_es_from_config


log = logging.getLogger(__name__)

curdir = os.path.dirname(os.path.abspath(__file__))
configfile = os.path.realpath(os.path.join(curdir, '../../test.ini'))
settings = get_appsettings(configfile)

alembic_scripts_folder = os.path.realpath(
    os.path.join(curdir, '../../alembic_migration'))

if settings['noauthorization']:
    log.warning('Authorization disabled for these tests')


def get_engine():
    return engine_from_config(settings, 'sqlalchemy.')


def _get_alembic_config():
    alembic_config = Config()
    alembic_config.set_main_option(
        'script_location', alembic_scripts_folder)
    alembic_config.set_main_option(
        'sqlalchemy.url', settings['sqlalchemy.url'])
    alembic_config.set_main_option(
        'version_table_schema', 'alembic')
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
            DocumentLocale(title='', description='Moi', lang='fr')],
        geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'))

    contributor = User(
        name='Contributor',
        username='contributor', email='contributor@camptocamp.org',
        forum_username='contributor', password='super pass',
        email_validated=True, profile=contributor_profile)

    contributor2_profile = UserProfile(
        categories=['amateur'],
        locales=[DocumentLocale(title='...', lang='en')])

    contributor2 = User(
        name='Contributor 2',
        username='contributor2', email='contributor2@camptocamp.org',
        forum_username='contributor2',
        password='better pass', email_validated=True,
        profile=contributor2_profile)

    contributor3_profile = UserProfile(
        categories=['amateur'],
        locales=[DocumentLocale(title='...', lang='en')])

    contributor3 = User(
        name='Contributor 3',
        username='contributor3', email='contributor3@camptocamp.org',
        forum_username='contributor3',
        password='poor pass', email_validated=True,
        profile=contributor3_profile)

    moderator_profile = UserProfile(
        categories=['mountain_guide'],
        locales=[DocumentLocale(title='', lang='en')])

    moderator = User(
        name='Moderator',
        username='moderator', email='moderator@camptocamp.org',
        forum_username='moderator',
        moderator=True, password='even better pass',
        email_validated=True, profile=moderator_profile)

    robot_profile = UserProfile(
        locales=[DocumentLocale(title='', lang='en')])

    robot = User(
        name='Robot',
        username='robot', email='robot@camptocamp.org',
        forum_username='robot',
        robot=True, password='bombproof pass',
        email_validated=True, profile=robot_profile)

    users = [robot, moderator, contributor, contributor2, contributor3]
    session.add_all(users)
    session.flush()

    domain = 'www.somewhere.com'
    sso_key = SsoKey(
        domain=domain,
        key=domain
    )
    session.add(sso_key)

    sso_external_id = SsoExternalId(
        domain=domain,
        external_id='1',
        user=contributor,
        token='token',
        expire=utc.localize(datetime.datetime.utcnow()),
    )
    session.add(sso_external_id)

    session.flush()

    key = settings['jwtauth.master_secret']
    algorithm = 'HS256'
    now = datetime.datetime.utcnow()
    exp = now + datetime.timedelta(weeks=10)

    for user in [robot, moderator, contributor, contributor2, contributor3]:
        claims = create_claims(user, exp)
        token = jwt.encode(claims, key=key, algorithm=algorithm). \
            decode('utf-8')
        add_or_retrieve_token(token, exp, user.id)
        global_userids[user.username] = user.id
        global_tokens[user.username] = token


def setup_package():

    # set up database
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
    with transaction.manager:
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


class AssertionsMixin(object):

    def assertCoodinateEquals(self, coord1, coord2):  # noqa
        self.assertEqual(len(coord1), len(coord2), 'not the same dimension')
        for i in range(0, len(coord1)):
            self.assertAlmostEqual(
                coord1[i], coord2[i],
                msg='{} does not almost equal {}'.format(coord1[i], coord2[i]))


class BaseTestCase(unittest.TestCase, AssertionsMixin):
    """The idea for unit tests is, that the database tables
    are created only once per test run and every test case uses a
    transaction which is rolled back at the end. This avoids that
    the database is set up and teared down after each test case.

    See also:
    http://www.sontek.net/blog/2011/12/01/writing_tests_for_pyramid_and_sqlalchemy.html
    """

    def __init__(self, *args, **kwargs):
        self.global_userids = global_userids
        self.global_tokens = global_tokens
        self.global_passwords = global_passwords
        self.settings = settings
        unittest.TestCase.__init__(self, *args, **kwargs)

    def get_email_box_length(self):
        return len(self.mailer.outbox)

    def get_last_email(self):
        outbox_count = self.get_email_box_length()
        return self.mailer.outbox[outbox_count - 1]

    @classmethod
    def setUpClass(cls):  # noqa
        cls.app = main({}, **settings)
        cls.engine = get_engine()
        cls.Session = sessionmaker()

    def setUp(self):  # noqa
        self.app = TestApp(self.app)
        registry = self.app.app.registry
        self.email_service = EmailService(settings)
        EmailService.instance = None

        self.config = testing.setUp()

        self.connection = self.engine.connect()

        # begin a non-ORM transaction
        self.trans = self.connection.begin()

        # DBSession is the scoped session manager used in the views,
        # reconfigure it to use this test's connection
        DBSession.configure(bind=self.connection)

        # create a session bound to the connection, this session is the one
        # used in the test code
        self.session = self.Session(bind=self.connection)

        self.queue_config = registry.queue_config
        reset_queue(self.queue_config)
        reset_cache_key()
        registry.feed_admin_user_account_id = None

    def tearDown(self):  # noqa
        # rollback - everything that happened with the Session above
        # (including calls to commit()) is rolled back.
        testing.tearDown()
        if not keep:
            self.trans.rollback()
        else:
            self.trans.commit()
        DBSession.remove()
        self.session.close()
        self.connection.close()

    def app_post_json(self, *args, **kwargs):
        return self.app_send_json('post', *args, **kwargs)

    def app_put_json(self, *args, **kwargs):
        return self.app_send_json('put', *args, **kwargs)

    def app_send_json(self, action, *args, **kwargs):
        kwargs = dict(kwargs)
        status = 200
        if 'status' in kwargs:
            status = kwargs['status']
            del kwargs['status']
        kwargs['expect_errors'] = True

        res = getattr(self.app, action + '_json')(*args, **kwargs)
        if status != '*' and res.status_code != status:
            errors = res.body if res.status_code == 400 else ''
            self.fail('Bad response: %s (not %d) : %s' % (
                res.status,
                status,
                errors))
        return res


def reset_queue(queue_config):
    queue = queue_config.queue(queue_config.connection)
    while queue.get():
        pass


def reset_cache_key():
    cache_version = settings['cache_version']
    caching.CACHE_VERSION = '{0}-{1}-{2}'.format(
        cache_version, int(time.time()), randint(0, 10**9))
    caching_common.cache_status = caching_common.CacheStatus()


setup_package()
