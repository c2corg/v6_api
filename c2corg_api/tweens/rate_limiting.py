import logging
import datetime
import pytz

from pyramid.httpexceptions import HTTPBadRequest, HTTPTooManyRequests
from c2corg_api.emails.email_service import get_email_service
from c2corg_api.views import http_error_handler
from c2corg_api.models import DBSession
from c2corg_api.models.user import User
from smtplib import SMTPAuthenticationError

log = logging.getLogger(__name__)


def rate_limiting_tween_factory(handler, registry):
    """ Add a rate limiting protection on write requests.
    """

    def tween(request):

        log.debug('RATE LIMITING FOR METHOD ' + request.method)

        # Only write requests are considered for rate limiting.
        if request.method not in ['POST', 'PUT', 'DELETE']:
            return handler(request)

        if request.authorization is None:
            # See comment of similar block in jwt_database_validation tween
            return handler(request)

        user = DBSession.query(User).get(request.authenticated_userid)
        if user is None:
            return http_error_handler(
                HTTPBadRequest('Unknown user'), request)

        now = datetime.datetime.now(pytz.utc)
        if user.ratelimit_reset is None or user.ratelimit_reset < now:
            # No window exists or it is expired: create a new one.
            span = int(registry.settings.get('rate_limiting.window_span'))
            limit = int(registry.settings.get(
                'rate_limiting.limit_robot' if user.robot else
                'rate_limiting.limit_moderator' if user.moderator else
                'rate_limiting.limit'))
            user.ratelimit_reset = now + datetime.timedelta(seconds=span)
            user.ratelimit_remaining = limit - 1
            log.warning('RATE LIMITING, CREATE WINDOW SPAN : {}'.format(
                user.ratelimit_reset
            ))

        elif user.ratelimit_remaining:
            user.ratelimit_remaining -= 1
            log.warning('RATE LIMITING, REQUESTS REMAINING FOR {} : {}'.format(
                user.id, user.ratelimit_remaining
            ))

        else:
            # User is rate limited
            log.warning('RATE LIMIT REACHED FOR USER {}'.format(user.id))

            # Count how many windows the user has been rate limited
            # and block them is too many.
            current_window = user.ratelimit_reset
            if user.ratelimit_last_blocked_window != current_window:
                user.ratelimit_last_blocked_window = current_window
                user.ratelimit_times += 1

                max_times = int(
                    registry.settings.get('rate_limiting.max_times'))
                if user.ratelimit_times > max_times:
                    log.warning('RATE LIMIT BLOCK USER {}'.format(user.id))
                    user.blocked = True

                # An alert message is sent to the moderators
                email_service = get_email_service(request)
                try:
                    email_service.send_rate_limiting_alert(user)
                except SMTPAuthenticationError:
                    log.error('RATE LIMIT ALERT MAIL : AUTHENTICATION ERROR')

            return http_error_handler(
                HTTPTooManyRequests('Rate limit reached'), request)

        return handler(request)

    return tween
