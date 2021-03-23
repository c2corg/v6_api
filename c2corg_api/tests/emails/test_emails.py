from c2corg_api.tests import BaseTestCase

from c2corg_api.models.user import User
from c2corg_api.emails.email_service import EmailLocalizator
from c2corg_api.models.common.attributes import default_langs

from unittest.mock import patch, ANY
from base64 import b64encode


class EmailTests(BaseTestCase):

    @patch('c2corg_api.emails.email_service.smtplib.SMTP')
    def test_send_email(self, smtp):
        self.email_service._send_email('toto@localhost', subject='s', body='b')

        smtp.assert_called_once_with(self.settings['mail.host'],
                                     port=self.settings['mail.port'])

        smtp.return_value.sendmail.assert_called_once_with(
            self.settings['mail.from'],
            'toto@localhost',
            ANY)

        msg = smtp.return_value.sendmail.call_args_list[0][0][2]
        self.assertIn('From: noreply@camptocamp.org', msg)
        self.assertIn('To: toto@localhost', msg)
        self.assertIn('Subject: s', msg)
        self.assertIn('Content-Type: text/plain; charset="utf-8"', msg)
        self.assertIn('Content-Transfer-Encoding: base64', msg)
        self.assertIn(b64encode('b'.encode('utf8')).decode('utf8'), msg)

    @patch('c2corg_api.emails.email_service.EmailService._send_email')
    def test_registration_confirmation(self, _send_email):
        user = User(email='me@localhost', lang='en')
        link = 'http://somelink'
        self.email_service.send_registration_confirmation(user, link)

        _send_email.assert_called_once_with(
            'me@localhost',
            subject='Registration on Camptocamp.org',
            body='''Hello

To activate your account click on http://somelink

Thank you very much
The Camptocamp.org team''')

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
