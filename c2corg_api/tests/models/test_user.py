from c2corg_api.models.user import User, Purpose

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

    def test_update_nonce(self):
        tony = User(email_validated=False)
        tony.update_validation_nonce(Purpose.registration, 2)

        def change_email():
            tony.update_validation_nonce(Purpose.change_email, 2)
        self.assertRaisesRegexp(
            Exception, 'Account not validated', change_email)

        tony.email_validated = True
        change_email()
