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
    def test_validate_password(self):
        tony = User(
            username='tonymontana', email_validated=True,
            email='tony@montana.com', password='foobar'
        )

        self.assertFalse(tony.validate_password('foobare'))
        self.assertTrue(tony.validate_password('foobar'))
