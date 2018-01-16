import logging

from pyramid.httpexceptions import HTTPUnauthorized, HTTPError
from c2corg_api.security.roles import is_valid_token, extract_token
from c2corg_api.views import http_error_handler, catch_all_error_handler

log = logging.getLogger(__name__)


def jwt_database_validation_tween_factory(handler, registry):
    """ Check validity of the JWT token.
    """

    def tween(request):

        log.debug('JWT VALIDATION')

        # forward requests without authorization
        if request.authorization is None:
            # Skipping validation if there is no authorization object.
            # This is dangerous since a bad ordering of this tween and the
            # cookie tween would bypass security
            return handler(request)

        # Finally, check database validation
        try:
            token = extract_token(request)
            valid = token and is_valid_token(token)
        except Exception as exc:
            if isinstance(exc, HTTPError):
                return http_error_handler(exc, request)
            else:
                return catch_all_error_handler(exc, request)

        if valid:
            return handler(request)
        else:
            return http_error_handler(
                HTTPUnauthorized('Invalid token'), request)

    return tween
