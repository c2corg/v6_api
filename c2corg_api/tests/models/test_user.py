import unittest

import bcrypt

from c2corg_api.models.user import User, Purpose, PasswordUtil
from c2corg_api.models.user_profile import UserProfile

from c2corg_api.tests import BaseTestCase


class TestPasswordUtil(unittest.TestCase):
    # 80 bytes in UTF-8: above bcrypt's 72-byte limit, with multi-byte
    # characters across the cut
    long_password = 'Élève 日本 ' * 5 + 'x' * 5

    def test_long_password(self):
        self.assertGreater(len(self.long_password.encode('utf-8')), 72)
        encrypted = PasswordUtil.encrypt_password(self.long_password)

        self.assertTrue(
            PasswordUtil.is_password_valid(self.long_password, encrypted))
        self.assertFalse(
            PasswordUtil.is_password_valid('wrong password', encrypted))

    def test_hash_made_by_truncating_bcrypt_still_valid(self):
        # bcrypt < 5 hashed only the first 72 bytes: hashes stored that way
        # must keep validating
        legacy = bcrypt.hashpw(
            self.long_password.encode('utf-8')[:72], bcrypt.gensalt())

        self.assertTrue(
            PasswordUtil.is_password_valid(self.long_password, legacy))
        self.assertTrue(PasswordUtil.is_password_valid(
            self.long_password, legacy.decode('utf-8')))

    def test_bytes_and_str_inputs(self):
        encrypted = PasswordUtil.encrypt_password(b'super pass')

        self.assertTrue(
            PasswordUtil.is_password_valid('super pass', encrypted))
        self.assertTrue(
            PasswordUtil.is_password_valid(b'super pass', encrypted))


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
        self.assertRaisesRegex(
            Exception, 'Account not validated', change_email)

        tony.email_validated = True
        change_email()

    def test_last_modified(self):
        """Check that the last modified field is set.
        """
        profile = UserProfile()
        self.session.add(profile)
        self.session.flush()

        user = User(
            id=profile.document_id,
            username='user', name='user', forum_username='user',
            email_validated=True, email='user@mail.com', password='foobar')
        self.session.add(user)
        self.session.flush()
        self.session.refresh(user)

        self.assertIsNotNone(user.last_modified)

        user.name = 'changed'
        self.session.flush()
        self.session.refresh(user)

        self.assertIsNotNone(user.last_modified)
