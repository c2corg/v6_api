from pyramid_mailer import get_mailer
from pyramid_mailer.message import Message

import logging

log = logging.getLogger(__name__)


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

    def _send_email(self, to_address, subject=None, body=None):
        """Send an email. This method may throw."""
        log.debug('Sending email to %s through %s' % (
            to_address, self.mail_server))
        msg = Message(
                subject=subject,
                sender=self.mail_from,
                recipients=[to_address],
                body=body)
        self.mailer.send_immediately(msg)

    def send_registration_confirmation(self, user, link):
        # TODO: handle i18n using user.lang
        self._send_email(
                user.email,
                subject='Registration on Camptocamp.org',
                body='To activate account click on %s' % link)

    def send_request_change_password(self, user, link):
        # TODO: handle i18n using user.lang
        self._send_email(
                user.email,
                subject='Password change on Camptocamp.org',
                body='To change your password click on %s' % link)

    def send_change_email_confirmation(self, user, link):
        # TODO: handle i18n using user.lang
        self._send_email(
                user.email_to_validate,
                subject='Email change on Camptocamp.org',
                body='To activate your new email click on %s' % link)


def get_email_service(request):
    if not EmailService.instance:
        mailer = get_mailer(request)
        settings = request.registry.settings
        EmailService.instance = EmailService(mailer, settings)
    return EmailService.instance
