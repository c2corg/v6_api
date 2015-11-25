from c2corg_api.models.user import User

from c2corg_api.tests import BaseTestCase


class SessionStub():
    def __init__(self):
        self.updated = False

    def add(self, arg2):
        self.updated = True

    def flush(self):
        self.updated = True


class Testuser(BaseTestCase):
    def assertPassword(self, user, password, expect_valid, expect_update=False):  # noqa
        session = SessionStub()
        valid = user.validate_password(password, session)
        self.assertTrue(expect_update == session.updated)
        self.assertTrue(expect_valid == valid)

    def test_validate_password(self):
        tony = User(
            username='tonymontana',
            email='tony@montana.com', password='foobar'
        )

        self.assertPassword(tony, 'foobare', False)
        self.assertPassword(tony, 'foobar', True)

        tony.set_temp_password('bouchon')
        self.assertPassword(tony, 'foobare', False)
        self.assertPassword(tony, 'foobar', True)
        self.assertPassword(tony, 'bouchon', True, expect_update=True)
