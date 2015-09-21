import os
from sqlalchemy import engine_from_config
from sqlalchemy.orm import sessionmaker
from pyramid.paster import get_appsettings
from pyramid import testing
import unittest
from webtest import TestApp

from c2corg_api import main
from c2corg_api.models import *  # noqa
from c2corg_api.scripts import initializedb

curdir = os.path.dirname(os.path.abspath(__file__))
configfile = os.path.realpath(os.path.join(curdir, '../../test.ini'))
settings = get_appsettings(configfile)


def get_engine():
    return engine_from_config(settings, 'sqlalchemy.')


def setup_package():
    # set up database
    engine = get_engine()
    DBSession.configure(bind=engine)
    initializedb.setup_db(engine, DBSession)
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
    @classmethod
    def setUpClass(cls):  # noqa
        cls.app = main({}, **settings)
        cls.engine = get_engine()
        cls.Session = sessionmaker()

    def setUp(self):  # noqa
        self.app = TestApp(self.app)
        self.config = testing.setUp()

        connection = self.engine.connect()

        # begin a non-ORM transaction
        self.trans = connection.begin()

        # DBSession is the scoped session manager used in the views,
        # reconfigure it to use this test's connection
        DBSession.configure(bind=connection)

        # create a session bound the connection, this session is the one
        # used in the test code
        self.session = self.Session(bind=connection)

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
