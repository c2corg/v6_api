import unittest
from unittest.mock import patch

from c2corg_api.httpexceptions import HTTPTooManyRequests
from c2corg_api.tweens.rate_limiting import (
    ANONYMOUS_RATE_LIMITED_BUCKETS,
    _check_anonymous_rate_limit,
    _client_ip,
    _is_anonymous_request_rate_limited,
    rate_limit_error,
)


class _Request:
    """The part of a request the rate limiting reads."""

    def __init__(self):
        self.method = 'GET'
        self.path = '/'
        self.headers = {}
        self.remote_addr = None
        self.authorization = None


class FakeRedis:
    """
    A minimal in-memory stand-in for the Redis client API.

    Only covers the subset used for anonymous rate limiting
    (`incr`/`expire`), so that the logic can be unit tested without a
    running Redis server.
    """

    def __init__(self):
        """Initialize empty in-memory counters and expirations."""
        self._counters = {}
        self.expirations = {}

    def incr(self, key):
        self._counters[key] = self._counters.get(key, 0) + 1
        return self._counters[key]

    def expire(self, key, ttl):
        self.expirations[key] = ttl


class FailingRedis:
    def incr(self, key):
        raise ConnectionError('redis is down')


class DummyRegistry:
    def __init__(self, settings):
        """Wrap `settings` in a Pyramid-registry-like object."""
        self.settings = settings


class TestClientIp:
    def test_uses_x_forwarded_for_when_present(self):
        request = _Request()
        request.headers['X-Forwarded-For'] = '203.0.113.5, 10.0.0.1'
        assert _client_ip(request) == '203.0.113.5'

    def test_falls_back_to_remote_addr(self):
        request = _Request()
        request.remote_addr = '198.51.100.7'
        assert _client_ip(request) == '198.51.100.7'


class TestIsAnonymousRequestRateLimited:
    def test_allows_requests_under_the_limit(self):
        redis_client = FakeRedis()
        for _ in range(3):
            limited = _is_anonymous_request_rate_limited(
                redis_client, 'k', window_span=60, limit=3
            )
        assert not limited

    def test_blocks_requests_over_the_limit(self):
        redis_client = FakeRedis()
        limited = None
        for _ in range(4):
            limited = _is_anonymous_request_rate_limited(
                redis_client, 'k', window_span=60, limit=3
            )
        assert limited

    def test_sets_expiration_only_on_first_increment(self):
        redis_client = FakeRedis()
        _is_anonymous_request_rate_limited(redis_client, 'k', window_span=42, limit=3)
        _is_anonymous_request_rate_limited(redis_client, 'k', window_span=42, limit=3)
        assert redis_client.expirations == {'k': 42}

    def test_fails_open_when_redis_client_is_none(self):
        limited = _is_anonymous_request_rate_limited(None, 'k', window_span=60, limit=1)
        assert not limited

    def test_fails_open_on_redis_error(self):
        limited = _is_anonymous_request_rate_limited(
            FailingRedis(), 'k', window_span=60, limit=1
        )
        assert not limited


class TestCheckAnonymousRateLimit:
    def _make_request(self, ip='192.0.2.1'):
        request = _Request()
        request.remote_addr = ip
        return request

    @patch('c2corg_api.tweens.rate_limiting._get_anonymous_rate_limit_redis_client')
    def test_blocks_after_the_configured_limit(self, get_client):
        redis_client = FakeRedis()
        get_client.return_value = redis_client
        registry = DummyRegistry(
            {
                'rate_limiting.anonymous_window_span': '60',
                'rate_limiting.anonymous_limit': '2',
            }
        )
        request = self._make_request()

        assert not _check_anonymous_rate_limit(request, registry.settings, 'login')
        assert not _check_anonymous_rate_limit(request, registry.settings, 'login')
        assert _check_anonymous_rate_limit(request, registry.settings, 'login')

    @patch('c2corg_api.tweens.rate_limiting._get_anonymous_rate_limit_redis_client')
    def test_different_ips_are_tracked_independently(self, get_client):
        redis_client = FakeRedis()
        get_client.return_value = redis_client
        registry = DummyRegistry(
            {
                'rate_limiting.anonymous_window_span': '60',
                'rate_limiting.anonymous_limit': '1',
            }
        )

        request_a = self._make_request('192.0.2.1')
        request_b = self._make_request('192.0.2.2')

        assert not _check_anonymous_rate_limit(request_a, registry.settings, 'login')
        # request_a is now at the limit, but request_b is a different IP
        assert not _check_anonymous_rate_limit(request_b, registry.settings, 'login')
        assert _check_anonymous_rate_limit(request_a, registry.settings, 'login')

    @patch('c2corg_api.tweens.rate_limiting._get_anonymous_rate_limit_redis_client')
    def test_different_buckets_are_tracked_independently(self, get_client):
        redis_client = FakeRedis()
        get_client.return_value = redis_client
        registry = DummyRegistry(
            {
                'rate_limiting.anonymous_window_span': '60',
                'rate_limiting.anonymous_limit': '1',
            }
        )
        request = self._make_request()

        assert not _check_anonymous_rate_limit(request, registry.settings, 'login')
        # a different bucket (account recovery) has its own counter
        assert not _check_anonymous_rate_limit(
            request, registry.settings, 'account_recovery'
        )


class TestRateLimitingTweenAnonymous:
    """
    Test that the tween routes anonymous requests correctly.

    Requests to the configured protected paths must go through the
    anonymous rate limiter, and every other anonymous request must be
    left untouched.
    """

    def _make_request(self, method, path):
        request = _Request()
        request.method = method
        request.path = path
        request.authorization = None
        return request

    def test_known_paths_are_covered(self):
        assert ANONYMOUS_RATE_LIMITED_BUCKETS['/users/login'] == 'login'
        assert (
            ANONYMOUS_RATE_LIMITED_BUCKETS['/users/request_password_change']
            == 'account_recovery'
        )

    @patch('c2corg_api.tweens.rate_limiting._check_anonymous_rate_limit')
    def test_login_is_blocked_when_rate_limited(self, check):
        check.return_value = True
        request = self._make_request('POST', '/users/login')

        error = rate_limit_error(request, {})

        assert isinstance(error, HTTPTooManyRequests)
        check.assert_called_once_with(request, {}, 'login')

    @patch('c2corg_api.tweens.rate_limiting._check_anonymous_rate_limit')
    def test_login_is_allowed_when_not_rate_limited(self, check):
        check.return_value = False
        request = self._make_request('POST', '/users/login')

        assert rate_limit_error(request, {}) is None
        check.assert_called_once()

    @patch('c2corg_api.tweens.rate_limiting._check_anonymous_rate_limit')
    def test_unrelated_anonymous_paths_are_not_rate_limited(self, check):
        request = self._make_request('POST', '/waypoints')

        assert rate_limit_error(request, {}) is None
        check.assert_not_called()

    @patch('c2corg_api.tweens.rate_limiting._check_anonymous_rate_limit')
    def test_get_requests_are_never_rate_limited(self, check):
        request = self._make_request('GET', '/users/login')

        assert rate_limit_error(request, {}) is None
        check.assert_not_called()


if __name__ == '__main__':
    unittest.main()
