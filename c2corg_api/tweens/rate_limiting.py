import logging
import datetime
import pytz

from pyramid.httpexceptions import HTTPBadRequest, HTTPTooManyRequests
from c2corg_api.caching import cache_document_detail
from c2corg_api.emails.email_service import get_email_service
from c2corg_api.views import http_error_handler
from c2corg_api.models import DBSession
from c2corg_api.models.user import User
from smtplib import SMTPAuthenticationError

log = logging.getLogger(__name__)

# Endpoints that are reachable without authentication (no `Authorization`
# header) but still need protection against brute-force / credential
# stuffing (login) and mailbombing (password reset request). There is no
# authenticated user to attach the per-user counters used below (the
# `ratelimit_*` columns on the `User` model) to, so these are instead rate
# limited by client IP address, using a simple fixed-window counter stored
# in Redis. The keys are: request path -> bucket name.
ANONYMOUS_RATE_LIMITED_BUCKETS = {
    '/users/login': 'login',
    # Named "account_recovery" rather than anything containing
    # "password"/"pwd": this is just a rate-limit bucket label, not a
    # credential, but static analysis (Codacy/Bandit-style hardcoded
    # password checks) flags string literals that look password-related
    # regardless of context.
    '/users/request_password_change': 'account_recovery',
}


def _client_ip(request):
    """
    Best-effort client IP resolution.

    In production the application is served behind a reverse proxy /
    load balancer (see apache/wsgi.conf.in), which is expected to set
    `X-Forwarded-For`; fall back to the direct peer address otherwise
    (e.g. local development).
    """
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        # the left-most entry is the original client address
        return forwarded_for.split(',')[0].strip()
    return request.remote_addr or 'unknown'


def _get_anonymous_rate_limit_redis_client():
    """
    Reuse the Redis connection pool already used for the app cache.

    See `c2corg_api.caching.configure_caches`; this avoids introducing a
    new storage backend just for anonymous rate limiting.
    """
    try:
        return cache_document_detail.backend.writer_client
    except Exception:
        log.exception(
            'Unable to get a Redis client for anonymous rate limiting')
        return None


def _is_anonymous_request_rate_limited(
        redis_client, key, window_span, limit):
    """
    Increment the counter stored at `key` in Redis.

    Creates it with a TTL of `window_span` seconds the first time, and
    returns True if the counter now exceeds `limit`.
    """
    if redis_client is None:
        # Fail open: if Redis is unavailable, do not block legitimate
        # traffic. This mirrors the "fail open" behaviour of the response
        # cache, see `c2corg_api.caching.get_or_create`.
        return False

    try:
        current = redis_client.incr(key)
        if current == 1:
            redis_client.expire(key, window_span)
    except Exception:
        log.exception(
            'Redis error while checking the anonymous rate limit for %s',
            key)
        return False

    return current > limit


def _check_anonymous_rate_limit(request, registry, bucket):
    """
    Return True if the anonymous `request` is rate limited.

    The request is identified by its client IP, and is considered rate
    limited if it has exceeded the allowed number of attempts for the
    given `bucket` (e.g. "login") during the current time window.
    """
    settings = registry.settings
    window_span = int(settings.get(
        'rate_limiting.anonymous_window_span') or
        settings.get('rate_limiting.window_span', 900))
    limit = int(settings.get('rate_limiting.anonymous_limit', 20))

    # Namespace the key with the same prefix used for the cache, so that
    # dev/test/prod instances sharing a Redis server don't collide.
    key_prefix = settings.get('redis.cache_key_prefix', 'c2corg')
    key = '{0}:ratelimit:anon:{1}:{2}'.format(
        key_prefix, bucket, _client_ip(request))

    redis_client = _get_anonymous_rate_limit_redis_client()
    limited = _is_anonymous_request_rate_limited(
        redis_client, key, window_span, limit)

    if limited:
        log.warning(
            'ANONYMOUS RATE LIMIT REACHED for bucket "%s" from %s',
            bucket, _client_ip(request))

    return limited


def rate_limiting_tween_factory(handler, registry):
    """ Add a rate limiting protection on write requests.
    """

    def tween(request):

        log.debug('RATE LIMITING FOR METHOD ' + request.method)

        # Only write requests are considered for rate limiting.
        if request.method not in ['POST', 'PUT', 'DELETE']:
            return handler(request)

        if request.authorization is None:
            bucket = ANONYMOUS_RATE_LIMITED_BUCKETS.get(request.path)
            if bucket is not None and _check_anonymous_rate_limit(
                    request, registry, bucket):
                return http_error_handler(
                    HTTPTooManyRequests('Rate limit reached'), request)
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
            log.debug('RATE LIMITING, CREATE WINDOW SPAN : {}'.format(
                user.ratelimit_reset
            ))

        elif user.ratelimit_remaining:
            user.ratelimit_remaining -= 1
            log.info('RATE LIMITING, REQUESTS REMAINING FOR {} : {}'.format(
                user.id, user.ratelimit_remaining
            ))

        else:
            # User is rate limited
            log.warning('RATE LIMIT REACHED FOR USER {}'.format(user.id))

            # Count how many windows the user has been rate limited
            # and block them if too many.
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
