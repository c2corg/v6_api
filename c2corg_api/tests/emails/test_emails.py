import pytest
from base64 import b64encode
from unittest.mock import ANY, patch

from c2corg_api.emails.email_service import EmailLocalizator
from c2corg_api.models.common.attributes import DefaultLangs
from c2corg_api.models.user import User
from c2corg_api.tests import BaseTestCase, settings


class EmailTests(BaseTestCase):
    @patch('c2corg_api.emails.email_service.smtplib.SMTP')
    def test_send_email(self, smtp):
        self.email_service._send_email('toto@localhost', subject='s', body='b')

        smtp.assert_called_once_with(settings['mail.host'], port=settings['mail.port'])

        smtp.return_value.sendmail.assert_called_once_with(
            settings['mail.from'], 'toto@localhost', ANY
        )

        msg = smtp.return_value.sendmail.call_args_list[0][0][2]
        assert 'From: noreply@camptocamp.org' in msg
        assert 'To: toto@localhost' in msg
        assert 'Subject: s' in msg
        assert 'Content-Type: text/plain; charset="utf-8"' in msg
        assert 'Content-Transfer-Encoding: base64' in msg
        assert b64encode('b'.encode('utf8')).decode('utf8') in msg

    @patch('c2corg_api.emails.email_service.EmailService._send_email')
    def test_registration_confirmation(self, _send_email):
        user = User(email='me@localhost', lang='en')
        link = 'http://somelink'
        self.email_service.send_registration_confirmation(user, link)

        _send_email.assert_called_once_with(
            'me@localhost',
            subject='Registration on Camptocamp.org',
            body="""Hello

To activate your account click on http://somelink

Thank you very much
The Camptocamp.org team""",
        )

    def test_localization(self):
        localizator = EmailLocalizator()
        for key in ['registration', 'password_change']:
            for lang in DefaultLangs:
                subject = localizator.get_translation(lang, key + '_subject')
                body = localizator.get_translation(lang, key + '_body')
                assert len(subject) > 0
                assert len(body) > 0
                assert '%s' in body

        def badlang():
            localizator.get_translation('toto', 'registration_subject')

        pytest.raises(Exception, badlang)
