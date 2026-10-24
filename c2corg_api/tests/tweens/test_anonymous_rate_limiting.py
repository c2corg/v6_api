import unittest
from unittest.mock import Mock, patch

from pyramid.httpexceptions import HTTPTooManyRequests
from pyramid.testing import DummyRequest

from c2corg_api.tweens.rate_limiting import (
    ANONYMOUS_RATE_LIMITED_BUCKETS,
    _check_anonymous_rate_limit,
    _client_ip,
    _is_anonymous_request_rate_limited,
    rate_limiting_tween_factory,
)


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
        request = DummyRequest()
        request.headers['X-Forwarded-For'] = '203.0.113.5, 10.0.0.1'
        assert _client_ip(request) == '203.0.113.5'

    def test_falls_back_to_remote_addr(self):
        request = DummyRequest()
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
        request = DummyRequest()
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

        assert not _check_anonymous_rate_limit(request, registry, 'login')
        assert not _check_anonymous_rate_limit(request, registry, 'login')
        assert _check_anonymous_rate_limit(request, registry, 'login')

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

        assert not _check_anonymous_rate_limit(request_a, registry, 'login')
        # request_a is now at the limit, but request_b is a different IP
        assert not _check_anonymous_rate_limit(request_b, registry, 'login')
        assert _check_anonymous_rate_limit(request_a, registry, 'login')

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

        assert not _check_anonymous_rate_limit(request, registry, 'login')
        # a different bucket (account recovery) has its own counter
        assert not _check_anonymous_rate_limit(request, registry, 'account_recovery')


class TestRateLimitingTweenAnonymous:
    """
    Test that the tween routes anonymous requests correctly.

    Requests to the configured protected paths must go through the
    anonymous rate limiter, and every other anonymous request must be
    left untouched.
    """

    def _make_request(self, method, path):
        request = DummyRequest()
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

    @patch('c2corg_api.tweens.rate_limiting.http_error_handler')
    @patch('c2corg_api.tweens.rate_limiting._check_anonymous_rate_limit')
    def test_login_is_blocked_when_rate_limited(self, check, error_handler):
        check.return_value = True
        error_handler.return_value = 'too many requests'
        handler = Mock()
        tween = rate_limiting_tween_factory(handler, DummyRegistry({}))

        request = self._make_request('POST', '/users/login')
        response = tween(request)

        handler.assert_not_called()
        assert error_handler.call_count == 1
        (exc, req), _ = error_handler.call_args
        assert isinstance(exc, HTTPTooManyRequests)
        assert req is request
        assert response == 'too many requests'

    @patch('c2corg_api.tweens.rate_limiting._check_anonymous_rate_limit')
    def test_login_is_allowed_when_not_rate_limited(self, check):
        check.return_value = False
        handler = Mock(return_value='handled')
        tween = rate_limiting_tween_factory(handler, DummyRegistry({}))

        request = self._make_request('POST', '/users/login')
        response = tween(request)

        handler.assert_called_once_with(request)
        assert response == 'handled'

    @patch('c2corg_api.tweens.rate_limiting._check_anonymous_rate_limit')
    def test_unrelated_anonymous_paths_are_not_rate_limited(self, check):
        handler = Mock(return_value='handled')
        tween = rate_limiting_tween_factory(handler, DummyRegistry({}))

        request = self._make_request('POST', '/waypoints')
        response = tween(request)

        check.assert_not_called()
        handler.assert_called_once_with(request)
        assert response == 'handled'

    def test_get_requests_are_never_rate_limited(self):
        handler = Mock(return_value='handled')
        tween = rate_limiting_tween_factory(handler, DummyRegistry({}))

        request = self._make_request('GET', '/users/login')
        response = tween(request)

        handler.assert_called_once_with(request)
        assert response == 'handled'


if __name__ == '__main__':
    unittest.main()
