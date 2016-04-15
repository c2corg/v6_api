from c2corg_api.tests import BaseTestCase

from c2corg_api.models.user import User
from c2corg_api.emails.email_service import EmailLocalizator
from c2corg_common.attributes import default_langs


class EmailTests(BaseTestCase):

    def test_send_email(self):
        outbox_count = self.get_email_box_length()
        self.email_service._send_email('toto@localhost', subject='s', body='b')
        self.assertEqual(self.get_email_box_length(), outbox_count + 1)
        self.assertEqual(self.get_last_email().subject, "s")
        self.assertEqual(self.get_last_email().body, "b")

    def test_registration_confirmation(self):
        user = User(email='me@localhost', lang='en')
        link = 'http://somelink'
        outbox_count = self.get_email_box_length()
        self.email_service.send_registration_confirmation(user, link)
        self.assertEqual(self.get_email_box_length(), outbox_count + 1)
        self.assertIn("Registration", self.get_last_email().subject)
        self.assertIn("To activate", self.get_last_email().body)
        self.assertIn(link, self.get_last_email().body)

    def test_localization(self):
        localizator = EmailLocalizator()
        for key in ['registration', 'password_change']:
            for lang in default_langs:
                subject = localizator.get_translation(lang, key + '_subject')
                body = localizator.get_translation(lang, key + '_body')
                self.assertTrue(len(subject) > 0)
                self.assertTrue(len(body) > 0)
                self.assertIn('%s', body)

        def badlang():
            localizator.get_translation('toto', 'registration_subject')
        self.assertRaises(Exception, badlang)
