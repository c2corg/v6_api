import os
from sqlalchemy import engine_from_config
from sqlalchemy.orm import sessionmaker
from pyramid.paster import get_appsettings
from pyramid import testing
import unittest
from webtest import TestApp

from app_api import main
from app_api.models import *  # noqa


curdir = os.path.dirname(os.path.abspath(__file__))
configfile = os.path.realpath(os.path.join(curdir, '../../test.ini'))
settings = get_appsettings(configfile)


def get_engine():
    return engine_from_config(settings, 'sqlalchemy.')


def setup_package():
    # set up database
    engine = get_engine()
    DBSession.configure(bind=engine)
    Base.metadata.create_all(engine)

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

        # bind an individual Session to the connection
        # Next line is needed to make several tests run in a row.
        # See https://github.com/Pylons/webtest/issues/5
        # FIXME Is there a better solution?
        DBSession.remove()
        DBSession.configure(bind=connection)
        self.session = self.Session(bind=connection)
        Base.session = self.session

    def tearDown(self):  # noqa
        # rollback - everything that happened with the Session above
        # (including calls to commit()) is rolled back.
        testing.tearDown()
        if not keep:
            self.trans.rollback()
        else:
            self.trans.commit()
        self.session.close()
