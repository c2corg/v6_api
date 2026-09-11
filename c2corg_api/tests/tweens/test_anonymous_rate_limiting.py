import unittest
from unittest.mock import Mock, patch

from pyramid.testing import DummyRequest
from pyramid.httpexceptions import HTTPTooManyRequests

from c2corg_api.tweens.rate_limiting import (
    ANONYMOUS_RATE_LIMITED_BUCKETS,
    _check_anonymous_rate_limit,
    _client_ip,
    _is_anonymous_request_rate_limited,
    rate_limiting_tween_factory,
)


class FakeRedis(object):
    """ A minimal in-memory stand-in for the subset of the Redis client API
    used for anonymous rate limiting (`incr`/`expire`), so that the logic
    can be unit tested without a running Redis server.
    """

    def __init__(self):
        self._counters = {}
        self.expirations = {}

    def incr(self, key):
        self._counters[key] = self._counters.get(key, 0) + 1
        return self._counters[key]

    def expire(self, key, ttl):
        self.expirations[key] = ttl


class FailingRedis(object):
    def incr(self, key):
        raise ConnectionError('redis is down')


class DummyRegistry(object):
    def __init__(self, settings):
        self.settings = settings


class ClientIpTest(unittest.TestCase):

    def test_uses_x_forwarded_for_when_present(self):
        request = DummyRequest()
        request.headers['X-Forwarded-For'] = '203.0.113.5, 10.0.0.1'
        self.assertEqual(_client_ip(request), '203.0.113.5')

    def test_falls_back_to_remote_addr(self):
        request = DummyRequest()
        request.remote_addr = '198.51.100.7'
        self.assertEqual(_client_ip(request), '198.51.100.7')


class IsAnonymousRequestRateLimitedTest(unittest.TestCase):

    def test_allows_requests_under_the_limit(self):
        redis_client = FakeRedis()
        for _ in range(3):
            limited = _is_anonymous_request_rate_limited(
                redis_client, 'k', window_span=60, limit=3)
        self.assertFalse(limited)

    def test_blocks_requests_over_the_limit(self):
        redis_client = FakeRedis()
        limited = None
        for _ in range(4):
            limited = _is_anonymous_request_rate_limited(
                redis_client, 'k', window_span=60, limit=3)
        self.assertTrue(limited)

    def test_sets_expiration_only_on_first_increment(self):
        redis_client = FakeRedis()
        _is_anonymous_request_rate_limited(
            redis_client, 'k', window_span=42, limit=3)
        _is_anonymous_request_rate_limited(
            redis_client, 'k', window_span=42, limit=3)
        self.assertEqual(redis_client.expirations, {'k': 42})

    def test_fails_open_when_redis_client_is_none(self):
        limited = _is_anonymous_request_rate_limited(
            None, 'k', window_span=60, limit=1)
        self.assertFalse(limited)

    def test_fails_open_on_redis_error(self):
        limited = _is_anonymous_request_rate_limited(
            FailingRedis(), 'k', window_span=60, limit=1)
        self.assertFalse(limited)


class CheckAnonymousRateLimitTest(unittest.TestCase):

    def _make_request(self, ip='192.0.2.1'):
        request = DummyRequest()
        request.remote_addr = ip
        return request

    @patch(
        'c2corg_api.tweens.rate_limiting.'
        '_get_anonymous_rate_limit_redis_client')
    def test_blocks_after_the_configured_limit(self, get_client):
        redis_client = FakeRedis()
        get_client.return_value = redis_client
        registry = DummyRegistry({
            'rate_limiting.anonymous_window_span': '60',
            'rate_limiting.anonymous_limit': '2',
        })
        request = self._make_request()

        self.assertFalse(
            _check_anonymous_rate_limit(request, registry, 'login'))
        self.assertFalse(
            _check_anonymous_rate_limit(request, registry, 'login'))
        self.assertTrue(
            _check_anonymous_rate_limit(request, registry, 'login'))

    @patch(
        'c2corg_api.tweens.rate_limiting.'
        '_get_anonymous_rate_limit_redis_client')
    def test_different_ips_are_tracked_independently(self, get_client):
        redis_client = FakeRedis()
        get_client.return_value = redis_client
        registry = DummyRegistry({
            'rate_limiting.anonymous_window_span': '60',
            'rate_limiting.anonymous_limit': '1',
        })

        request_a = self._make_request('192.0.2.1')
        request_b = self._make_request('192.0.2.2')

        self.assertFalse(
            _check_anonymous_rate_limit(request_a, registry, 'login'))
        # request_a is now at the limit, but request_b is a different IP
        self.assertFalse(
            _check_anonymous_rate_limit(request_b, registry, 'login'))
        self.assertTrue(
            _check_anonymous_rate_limit(request_a, registry, 'login'))

    @patch(
        'c2corg_api.tweens.rate_limiting.'
        '_get_anonymous_rate_limit_redis_client')
    def test_different_buckets_are_tracked_independently(self, get_client):
        redis_client = FakeRedis()
        get_client.return_value = redis_client
        registry = DummyRegistry({
            'rate_limiting.anonymous_window_span': '60',
            'rate_limiting.anonymous_limit': '1',
        })
        request = self._make_request()

        self.assertFalse(
            _check_anonymous_rate_limit(request, registry, 'login'))
        # a different bucket (password reset) has its own counter
        self.assertFalse(
            _check_anonymous_rate_limit(
                request, registry, 'password_reset'))


class RateLimitingTweenAnonymousTest(unittest.TestCase):
    """ Checks that the tween routes anonymous requests to the configured
    protected paths through the anonymous rate limiter, and leaves every
    other anonymous request untouched.
    """

    def _make_request(self, method, path):
        request = DummyRequest()
        request.method = method
        request.path = path
        request.authorization = None
        return request

    def test_known_paths_are_covered(self):
        self.assertEqual(
            ANONYMOUS_RATE_LIMITED_BUCKETS['/users/login'], 'login')
        self.assertEqual(
            ANONYMOUS_RATE_LIMITED_BUCKETS['/users/request_password_change'],
            'password_reset')

    @patch('c2corg_api.tweens.rate_limiting.http_error_handler')
    @patch('c2corg_api.tweens.rate_limiting._check_anonymous_rate_limit')
    def test_login_is_blocked_when_rate_limited(self, check, error_handler):
        check.return_value = True
        error_handler.return_value = 'too many requests'
        handler = Mock()
        tween = rate_limiting_tween_factory(
            handler, DummyRegistry({}))

        request = self._make_request('POST', '/users/login')
        response = tween(request)

        handler.assert_not_called()
        self.assertEqual(error_handler.call_count, 1)
        (exc, req), _ = error_handler.call_args
        self.assertIsInstance(exc, HTTPTooManyRequests)
        self.assertIs(req, request)
        self.assertEqual(response, 'too many requests')

    @patch('c2corg_api.tweens.rate_limiting._check_anonymous_rate_limit')
    def test_login_is_allowed_when_not_rate_limited(self, check):
        check.return_value = False
        handler = Mock(return_value='handled')
        tween = rate_limiting_tween_factory(
            handler, DummyRegistry({}))

        request = self._make_request('POST', '/users/login')
        response = tween(request)

        handler.assert_called_once_with(request)
        self.assertEqual(response, 'handled')

    @patch('c2corg_api.tweens.rate_limiting._check_anonymous_rate_limit')
    def test_unrelated_anonymous_paths_are_not_rate_limited(self, check):
        handler = Mock(return_value='handled')
        tween = rate_limiting_tween_factory(
            handler, DummyRegistry({}))

        request = self._make_request('POST', '/waypoints')
        response = tween(request)

        check.assert_not_called()
        handler.assert_called_once_with(request)
        self.assertEqual(response, 'handled')

    def test_get_requests_are_never_rate_limited(self):
        handler = Mock(return_value='handled')
        tween = rate_limiting_tween_factory(
            handler, DummyRegistry({}))

        request = self._make_request('GET', '/users/login')
        response = tween(request)

        handler.assert_called_once_with(request)
        self.assertEqual(response, 'handled')


if __name__ == '__main__':
    unittest.main()
