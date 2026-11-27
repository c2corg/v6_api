import bcrypt
import pytest

from c2corg_api.models.user import PasswordUtil, Purpose, User
from c2corg_api.models.user_profile import UserProfile

# 80 bytes in UTF-8: above bcrypt's 72-byte limit, with multi-byte
# characters across the cut
LONG_PASSWORD = 'Élève 日本 ' * 5 + 'x' * 5


def test_long_password():
    assert len(LONG_PASSWORD.encode('utf-8')) > 72
    encrypted = PasswordUtil.encrypt_password(LONG_PASSWORD)

    assert PasswordUtil.is_password_valid(LONG_PASSWORD, encrypted)
    assert not PasswordUtil.is_password_valid('wrong password', encrypted)


def test_hash_made_by_truncating_bcrypt_still_valid():
    # bcrypt < 5 hashed only the first 72 bytes: hashes stored that way
    # must keep validating
    legacy = bcrypt.hashpw(LONG_PASSWORD.encode('utf-8')[:72], bcrypt.gensalt())

    assert PasswordUtil.is_password_valid(LONG_PASSWORD, legacy)
    assert PasswordUtil.is_password_valid(LONG_PASSWORD, legacy.decode('utf-8'))


def test_bytes_and_str_inputs():
    encrypted = PasswordUtil.encrypt_password(b'super pass')

    assert PasswordUtil.is_password_valid('super pass', encrypted)
    assert PasswordUtil.is_password_valid(b'super pass', encrypted)


def test_validate_password():
    tony = User(
        username='tonymontana',
        email_validated=True,
        email='tony@montana.com',
        password='foobar',
    )

    assert not tony.validate_password('foobare')
    assert tony.validate_password('foobar')


def test_update_nonce():
    tony = User(email_validated=False)
    tony.update_validation_nonce(Purpose.registration, 2)

    def change_email():
        tony.update_validation_nonce(Purpose.change_email, 2)

    with pytest.raises(Exception, match='Account not validated'):
        change_email()

    tony.email_validated = True
    change_email()


def test_last_modified(session):
    """Check that the last modified field is set."""
    profile = UserProfile()
    session.add(profile)
    session.flush()

    user = User(
        id=profile.document_id,
        username='user',
        name='user',
        forum_username='user',
        email_validated=True,
        email='user@mail.com',
        password='foobar',
    )
    session.add(user)
    session.flush()
    session.refresh(user)

    assert user.last_modified is not None

    user.name = 'changed'
    session.flush()
    session.refresh(user)

    assert user.last_modified is not None
