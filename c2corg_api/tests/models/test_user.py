from c2corg_api.models.user import User

from c2corg_api.tests import BaseTestCase


class Testuser(BaseTestCase):

    def test_validate_password(self):
        tony = User(
            username='tonymontana',
            email='tony@montana.com', password='foobar'
        )

        self.assertFalse(tony.validate_password('foobare'))
        self.assertTrue(tony.validate_password('foobar'))
        tony.set_temp_password('bouchon')
        self.assertTrue(tony.validate_password('bouchon'))
