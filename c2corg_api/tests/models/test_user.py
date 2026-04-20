import pytest

from c2corg_api.models.user import Purpose, User
from c2corg_api.models.user_profile import UserProfile
from c2corg_api.tests import BaseTestCase


class Testuser(BaseTestCase):
    def test_validate_password(self):
        tony = User(
            username='tonymontana',
            email_validated=True,
            email='tony@montana.com',
            password='foobar',
        )

        assert not tony.validate_password('foobare')
        assert tony.validate_password('foobar')

    def test_update_nonce(self):
        tony = User(email_validated=False)
        tony.update_validation_nonce(Purpose.registration, 2)

        def change_email():
            tony.update_validation_nonce(Purpose.change_email, 2)

        with pytest.raises(Exception, match='Account not validated'):
            change_email()

        tony.email_validated = True
        change_email()

    def test_last_modified(self):
        """Check that the last modified field is set."""
        profile = UserProfile()
        self.session.add(profile)
        self.session.flush()

        user = User(
            id=profile.document_id,
            username='user',
            name='user',
            forum_username='user',
            email_validated=True,
            email='user@mail.com',
            password='foobar',
        )
        self.session.add(user)
        self.session.flush()
        self.session.refresh(user)

        assert user.last_modified is not None

        user.name = 'changed'
        self.session.flush()
        self.session.refresh(user)

        assert user.last_modified is not None
