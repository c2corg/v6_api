import transaction  # NOQA

from pyramid_mailer import get_mailer
from pyramid_mailer.message import Message, Attachment
from functools import lru_cache
from c2corg_common.attributes import default_langs

import logging
import os

log = logging.getLogger(__name__)


class EmailLocalizator(object):
    def __init__(self):
        self.default_lang = 'fr'

    @lru_cache(maxsize=None)
    def _get_file_content(self, lang, key):
        filepath = os.path.dirname(__file__) + '/i18n/%s/%s' % (lang, key)
        if not os.path.isfile(filepath):
            filepath = os.path.dirname(__file__) + '/i18n/%s/%s' % ('fr', key)
        f = open(filepath, 'r')
        return f.read().rstrip()  # No trailing new line in email subject!

    def get_translation(self, lang, key):
        if lang not in default_langs:
            raise Exception('Bad language' + lang)
        try:
            return self._get_file_content(lang, key)
        except:
            log.exception('The %s translation for %s could not be read' % (
                lang, key))
            return self._get_file_content('fr', key)


# See https://docs.python.org/3/library/smtplib.html#smtplib.SMTP.sendmail
# https://github.com/Pylons/pyramid_mailer
# http://docs.pylonsproject.org/projects/pyramid/en/latest/narr/i18n.html
class EmailService:
    instance = None

    def __init__(self, mailer, settings):
        self.mail_from = settings['mail.from']
        host = settings['mail.host']
        port = settings['mail.port']
        self.mail_server = '%s:%s' % (host, port)
        self.mailer = mailer
        self.settings = settings
        localizator = EmailLocalizator()
        self._ = lambda lang, key: localizator.get_translation(lang, key)

    def _send_email(self, to_address, subject=None, body=None):
        """Send an email. This method may throw."""
        log.debug('Sending email to %s through %s' % (
            to_address, self.mail_server))
        if body:
            # Convert body text to attachment instance
            # in order to force the transfer encoding to 8bit
            # instead of quoted-printable because of problems
            # with email services such as hotmail.
            body = Attachment(
                data=body,
                content_type='text/plain',
                transfer_encoding='8bit',
                disposition='inline')
        msg = Message(
                subject=subject,
                sender=self.mail_from,
                recipients=[to_address],
                body=body)
        self.mailer.send(msg)

    def _send_email_with_link(self, user, key, link):
        self._send_email(
                user.email,
                subject=self._(user.lang, key + '_subject'),
                body=self._(user.lang, key + '_body') % link)

    def send_registration_confirmation(self, user, link):
        self._send_email_with_link(user, 'registration', link)

    def send_request_change_password(self, user, link):
        self._send_email_with_link(user, 'password_change', link)

    def send_change_email_confirmation(self, user, link):
        self._send_email(
                user.email_to_validate,
                subject=self._(user.lang, 'email_change_subject'),
                body=self._(user.lang, 'email_change_body') % link)


def get_email_service(request):
    if not EmailService.instance:
        mailer = get_mailer(request)
        settings = request.registry.settings
        EmailService.instance = EmailService(mailer, settings)
    return EmailService.instance
