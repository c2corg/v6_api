import os

from c2corg_api.tests import BaseTestCase

from pyramid.paster import get_appsettings

from c2corg_api.models.user import User

curdir = os.path.dirname(os.path.abspath(__file__))
configfile = os.path.realpath(os.path.join(curdir, '../../../test.ini'))
settings = get_appsettings(configfile)


class EmailTests(BaseTestCase):

    def test_send_email(self):
        outbox_count = self.get_email_box_length()
        self.email_service._send_email('toto@localhost', subject='s', body='b')
        self.assertEqual(self.get_email_box_length(), outbox_count + 1)
        self.assertEqual(self.get_last_email().subject, "s")
        self.assertEqual(self.get_last_email().body, "b")

    def test_registration_confirmation(self):
        lang = 'fr'
        user = User(email='me@localhost')
        link = 'http://somelink'
        outbox_count = self.get_email_box_length()
        self.email_service.send_registration_confirmation(lang, user, link)
        self.assertEqual(self.get_email_box_length(), outbox_count + 1)
        self.assertIn("Inscription", self.get_last_email().subject)
        self.assertIn("Pour activer", self.get_last_email().body)
        self.assertIn(link, self.get_last_email().body)
