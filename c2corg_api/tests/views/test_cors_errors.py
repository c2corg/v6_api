import datetime
from unittest.mock import patch

from c2corg_api.models.user import User
from c2corg_api.tests.views import BaseTestRest

WAYPOINT = {
    'waypoint_type': 'summit',
    'elevation': 3779,
    'geometry': {'geom': '{"type": "Point", "coordinates": [635956, 5723604]}'},
    'locales': [{'lang': 'en', 'title': 'Mont Pourri'}],
}


class TestCorsOnErrors(BaseTestRest):
    """Error answers carry the CORS headers, or a browser hides them (#720, #730)."""

    def setUp(self):
        self.origin = self.settings['cors.allowed_origins'].split()[0]

    def assert_cors(self, response, origin):
        assert response.headers['Access-Control-Allow-Origin'] == origin
        assert response.headers['Access-Control-Expose-Headers'] == 'Content-Type'

    def test_invalid_token(self):
        # 401 from the JWT validation tween
        response = self.app.post_json(
            '/waypoints',
            WAYPOINT,
            headers={'Authorization': 'JWT token="not-a-token"', 'Origin': self.origin},
            status=401,
        )
        self.assert_cors(response, self.origin)

    def test_rate_limited(self):
        # 429 from the rate limiting tween
        user = self.session.get(User, self.global_userids['contributor'])
        user.ratelimit_reset = datetime.datetime.now(datetime.UTC) + datetime.timedelta(
            minutes=5
        )
        user.ratelimit_remaining = 0
        self.session.flush()
        headers = self.add_authorization_header(username='contributor')
        headers['Origin'] = self.origin
        with patch('c2corg_api.emails.email_service.EmailService._send_email'):
            response = self.app.post_json(
                '/waypoints', WAYPOINT, headers=headers, status=429
            )
        self.assert_cors(response, self.origin)

    def test_unexpected_error(self):
        # 500 from the catch-all error view of Pyramid: /getcoverage stays on
        # Pyramid for now (/health and /sitemaps moved to FastAPI, #2365)
        with patch(
            'c2corg_api.views.coverage.get_coverage',
            side_effect=RuntimeError('boom'),
        ):
            response = self.app.get(
                '/getcoverage',
                params={'lon': 6, 'lat': 45},
                headers={'Origin': self.origin},
                status=500,
            )
        self.assert_cors(response, self.origin)

    def test_unknown_route(self):
        # 404 answered by Pyramid itself, not by a Cornice view
        response = self.app.get(
            '/no-such-route', headers={'Origin': self.origin}, status=404
        )
        self.assert_cors(response, self.origin)

    def test_only_for_allowed_origins(self):
        response = self.app.post_json(
            '/waypoints',
            WAYPOINT,
            headers={
                'Authorization': 'JWT token="not-a-token"',
                'Origin': 'https://evil.example.org',
            },
            status=401,
        )
        assert 'Access-Control-Allow-Origin' not in response.headers

    def test_without_origin(self):
        response = self.app.post_json(
            '/waypoints',
            WAYPOINT,
            headers={'Authorization': 'JWT token="not-a-token"'},
            status=401,
        )
        assert 'Access-Control-Allow-Origin' not in response.headers
