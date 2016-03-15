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
        self.mailer = mailer
        self.settings = settings

    def _send_email(self, to_address, subject=None, body=None):
        """Send an email. This method may throw."""
        msg = Message(
                subject=subject,
                sender=self.mail_from,
                recipients=[to_address],
                body=body)
        self.mailer.send_immediately(msg)

    def send_registration_confirmation(self, lang, user, link):
        # TODO: handle i18n
        self._send_email(
                user.email,
                subject='Inscription sur Camptocamp.org',
                body='Pour activer votre compte cliquez sur %s' % link)


def get_email_service(request):
    if not EmailService.instance:
        mailer = get_mailer(request)
        settings = request.registry.settings
        EmailService.instance = EmailService(mailer, settings)
    return EmailService.instance


if __name__ == '__main__':
    import os
    import sys
    from pyramid.paster import get_appsettings
    from pyramid_mailer.mailer import Mailer
    curdir = os.path.dirname(os.path.abspath(__file__))
    configfile = os.path.realpath(os.path.join(curdir, '../../common.ini'))
    settings = get_appsettings(configfile)
    mailer = Mailer.from_settings(settings)

    EmailService(mailer, settings)._send_email(
            sys.argv[1],
            subject='Test send email élève forêt ça alors',
            body='body 日本国 http://localhost')
