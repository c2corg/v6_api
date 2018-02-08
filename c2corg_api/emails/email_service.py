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
            # in order to force the transfer encoding to base64
            # instead of quoted-printable because of problems
            # with email services such as hotmail.
            attachment = Attachment(
                data=body,
                content_type='text/plain',
                transfer_encoding='base64',
                disposition='inline')
        base_body = 'FIXME: base email body'
        msg = Message(
                subject=subject,
                sender=self.mail_from,
                recipients=[to_address],
                attachments=[attachment] if attachment else None,
                body=base_body)
        self.mailer.send(msg)

    def send_registration_confirmation(self, user, link):
        self._send_email(
                user.email,
                subject=self._(user.lang, 'registration_subject'),
                body=self._(user.lang, 'registration_body') % link)

    def send_request_change_password(self, user, link):
        body = self._(user.lang, 'password_change_body') % (
            link, user.username)
        self._send_email(
                user.email,
                subject=self._(user.lang, 'password_change_subject'),
                body=body)

    def send_change_email_confirmation(self, user, link):
        self._send_email(
                user.email_to_validate,
                subject=self._(user.lang, 'email_change_subject'),
                body=self._(user.lang, 'email_change_body') % link)

    def send_rate_limiting_alert(self, user):
        url = '{}/profiles/{}'.format(self.settings['ui.url'], user.id)
        if user.blocked:
            body = self._('fr', 'rate_limiting_blocked_alert_body') % (
                user.name, url)
        else:
            body = self._('fr', 'rate_limiting_alert_body') % (
                user.name, url, user.ratelimit_times)
        self._send_email(
                self.settings['rate_limiting.alert_address'],
                subject=self._('fr', 'rate_limiting_alert_subject'),
                body=body)


def get_email_service(request):
    if not EmailService.instance:
        mailer = get_mailer(request)
        settings = request.registry.settings
        EmailService.instance = EmailService(mailer, settings)
    return EmailService.instance
