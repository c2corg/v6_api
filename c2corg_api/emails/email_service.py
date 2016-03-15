import smtplib
from email.mime.text import MIMEText

import logging

log = logging.getLogger(__name__)


class EmailService:

    def _(self, lang, key):
        extended_key = lang + '_' + key
        if extended_key in settings:
            return settings[extended_key]
        log.warn('Untranslated string ' + extended_key)
        return settings['fr_' + key]


    def __init__(self, settings):
        self.mail_from = settings['mail.from']
        self.mail_host = settings['mail.host']
        self.mail_port = int(settings.get('mail.port', 0))
        self.mail_debug = int(settings.get('mail.debug', 0))
        self.settings = settings


    def _send_email(self, to_address, subject=None, body=None):
        """Send an email using smtplib.SMTP.sendmail. This method may throw.
        Use https://docs.python.org/3/library/smtplib.html#smtplib.SMTP.sendmail
        an alternative would be to use https://github.com/Pylons/pyramid_mailer.
        """
        msg = MIMEText(body, "plain", "utf-8")
        msg['Subject'] = subject
        msg['From'] = self.mail_from
        msg['To'] = to_address
        s = smtplib.SMTP(self.mail_host, self.mail_port)
        s.set_debuglevel(self.mail_debug)
        s.sendmail(self.mail_from, to_address, msg.as_string())
        s.quit()


    def send_registration_confirmation(self, lang, user, link):
        # TODO: handle i18n
        # http://docs.pylonsproject.org/projects/pyramid/en/latest/narr/i18n.html
        self._send_email(
                user.email,
                subject= 'Inscription sur Camptocamp.org',
                body='Pour activer votre compte cliquez sur %s' % link)


email_service_instance = None
def get_email_service(request):
    if not email_service_instance:
        email_service_instance = EmailService(request.registry.settings)
    return email_service_instance


if __name__ == '__main__':
    import os, sys
    from pyramid.paster import get_appsettings
    from c2corg_api.models.user import User
    curdir = os.path.dirname(os.path.abspath(__file__))
    configfile = os.path.realpath(os.path.join(curdir, '../../common.ini'))
    EmailService(get_appsettings(configfile))._send_email(
            sys.argv[1],
            subject='Test send email',
            body='body http://localhost')
