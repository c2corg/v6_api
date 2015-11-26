import jwt
import datetime

import transaction
import os
import logging
from sqlalchemy import engine_from_config
from sqlalchemy.orm import sessionmaker
from pyramid.paster import get_appsettings
from pyramid import testing
import unittest
from webtest import TestApp

from c2corg_api import main
from c2corg_api.models import *  # noqa
from c2corg_api.models.user import User
from c2corg_api.scripts import initializedb
from c2corg_api.security.roles import create_claims, add_token

log = logging.getLogger(__name__)

curdir = os.path.dirname(os.path.abspath(__file__))
configfile = os.path.realpath(os.path.join(curdir, '../../test.ini'))
settings = get_appsettings(configfile)


if settings['noauthorization']:
    log.warning('Authorization disabled for these tests')


def get_engine():
    return engine_from_config(settings, 'sqlalchemy.')

global_userids = {}
global_tokens = {}
global_passwords = {}


def _add_global_test_data(session):
    global_passwords['contributor'] = 'super pass'
    global_passwords['moderator'] = 'even better pass'

    contributor = User(
        username='contributor', email='contributor@camptocamp.org',
        password='super pass')

    moderator = User(
        username='moderator', email='moderator@camptocamp.org',
        moderator=True, password='even better pass')

    users = [moderator, contributor]
    session.add_all(users)
    session.flush()

    key = settings['jwtauth.master_secret']
    algorithm = 'HS256'
    now = datetime.datetime.utcnow()
    exp = now + datetime.timedelta(weeks=10)

    for user in [moderator, contributor]:
        claims = create_claims(user, exp)
        token = jwt.encode(claims, key=key, algorithm=algorithm)
        add_token(token, exp, user.id)
        global_userids[user.username] = user.id
        global_tokens[user.username] = token


def setup_package():
    # set up database
    engine = get_engine()
    DBSession.configure(bind=engine)
    Base.metadata.drop_all(engine)
    initializedb.setup_db(engine, DBSession)
    # Add test data needed for all tests
    with transaction.manager:
        _add_global_test_data(DBSession)
    DBSession.remove()

# keep the database schema after a test run (useful for debugging)
keep = False


def teardown_package():
    # tear down database
    engine = get_engine()
    if not keep:
        Base.metadata.drop_all(engine)


class BaseTestCase(unittest.TestCase):
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
        unittest.TestCase.__init__(self, *args, **kwargs)

    @classmethod
    def setUpClass(cls):  # noqa
        cls.app = main({}, **settings)
        cls.engine = get_engine()
        cls.Session = sessionmaker()

    def setUp(self):  # noqa
        self.app = TestApp(self.app)
        self.config = testing.setUp()

        self.connection = self.engine.connect()

        # begin a non-ORM transaction
        self.trans = self.connection.begin()

        # DBSession is the scoped session manager used in the views,
        # reconfigure it to use this test's connection
        DBSession.configure(bind=self.connection)

        # create a session bound the connection, this session is the one
        # used in the test code
        self.session = self.Session(bind=self.connection)

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
