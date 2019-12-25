import transaction  # NOQA

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from functools import lru_cache
from pyramid.settings import asbool
import smtplib

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
        with open(filepath, 'rU') as f:  # Use universal newline support.
            content = f.read().rstrip()  # No trailing new line in subject!
        return content

    def get_translation(self, lang, key):
        if lang not in default_langs:
            raise Exception('Bad language' + lang)
        try:
            return self._get_file_content(lang, key)
        except:  # noqa
            log.exception('The %s translation for %s could not be read' % (
                lang, key))
            return self._get_file_content('fr', key)


# See https://docs.python.org/3/library/smtplib.html#smtplib.SMTP.sendmail
# https://github.com/Pylons/pyramid_mailer
# http://docs.pylonsproject.org/projects/pyramid/en/latest/narr/i18n.html
class EmailService:
    instance = None

    def __init__(self, settings):
        self.mail_from = settings['mail.from']
        host = settings['mail.host']
        port = settings['mail.port']
        self.mail_server = '%s:%s' % (host, port)
        self.settings = settings
        localizator = EmailLocalizator()
        self._ = lambda lang, key: localizator.get_translation(lang, key)

    def _send_email(self, to_address, subject=None, body=None):
        log.debug('Sending email to %s through %s' % (
            to_address, self.mail_server))

        msg = MIMEMultipart()
        msg['From'] = self.mail_from
        msg['To'] = to_address
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        if asbool(self.settings.get('mail.ssl', False)):
            smtp = smtplib.SMTP_SSL(self.settings['mail.host'],
                                    port=self.settings['mail.port'])
        else:
            smtp = smtplib.SMTP(self.settings['mail.host'],
                                port=self.settings['mail.port'])

        if self.settings.get('mail.username', '') not in ('', 'None'):
            smtp.login(self.settings['mail.username'],
                       self.settings['mail.password'])

        if asbool(self.settings.get('mail.tls', False)):
            smtp.starttls()

        smtp.sendmail(self.mail_from, to_address, msg.as_string())
        smtp.close()

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
        settings = request.registry.settings
        EmailService.instance = EmailService(settings)
    return EmailService.instance
