import logging
import datetime
import pytz

from pyramid.httpexceptions import HTTPBadRequest, HTTPTooManyRequests
from c2corg_api.views import http_error_handler
from c2corg_api.models import DBSession
from c2corg_api.models.user import User

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
            limit = int(registry.settings.get('rate_limiting.limit'))
            user.ratelimit_reset = now + datetime.timedelta(seconds=span)
            user.ratelimit_limit = limit
            user.ratelimit_remaining = limit - 1
        elif user.ratelimit_remaining:
            user.ratelimit_remaining -= 1
        else:
            return http_error_handler(
                HTTPTooManyRequests('Rate limit reached'), request)

        return handler(request)

    return tween
