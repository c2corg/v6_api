from typing import Annotated
from unittest.mock import patch

from fastapi import Depends, Request

from c2corg_api.httpexceptions import HTTPBadRequest
from c2corg_api.models import DBSession
from c2corg_api.models.user import User
from c2corg_api.tests.views import BaseTestRest
from c2corg_api.views.resource import Errors
from c2corg_api.web.auth import CurrentUser, current_user
from c2corg_api.web.handlers import serve_write

PATH = '/test-write'


def _rename_user(request):
    """Rename the user, then answer as the request asks."""
    user = DBSession.get(User, request.authenticated_userid)
    user.name = 'renamed'
    DBSession.flush()
    outcome = request.json.get('outcome')
    if outcome == 'refused by the view':
        # as some views (e.g. a failed login): an error, nothing raised
        request.errors.add('body', 'outcome', 'refused by the view')
        request.errors.status = 401
        return None
    if outcome == 'client address':
        return {'client_addr': request.client_addr}
    if outcome == 'http_error':
        raise HTTPBadRequest('refused by the view')
    if outcome == 'bug':
        raise RuntimeError('boom')
    return {'name': user.name}


_rename_user.view_name = '_WriteView.collection_post'


def _require_outcome(request, **kwargs):
    outcome = request.json.get('outcome')
    if outcome == 'invalid':
        request.errors.add('body', 'outcome', 'invalid outcome')
    elif outcome == 'not yours':
        # as some validators: the errors of Cornice, and another status
        errors = Errors()
        errors.add('body', 'outcome', 'not yours')
        request.errors.extend(errors)
        request.errors.status = 403


class TestWrites(BaseTestRest):
    """The write path of web.handlers: rate limiting, checks, view, transaction."""

    def setUp(self):
        super().setUp()
        # The sessions of the requests join the transaction of the test in a
        # SAVEPOINT (conftest), so that a rollback really rolls the request back.
        self.fastapi_app = self.app.app.fastapi_app

        async def endpoint(
            request: Request,
            user: Annotated[CurrentUser | None, Depends(current_user)],
        ):
            return await serve_write(
                request,
                user,
                [_require_outcome],
                _rename_user,
                permission='authenticated',
                content_types=['application/json'],
            )

        self.fastapi_app.add_api_route(PATH, endpoint, methods=['POST'])
        self.user = self.session.get(User, self.global_userids['contributor'])
        self.name = self.user.name
        self.limit = int(self.settings['rate_limiting.limit'])

    def tearDown(self):
        DBSession.remove()
        self.fastapi_app.router.routes[:] = [
            r for r in self.fastapi_app.router.routes if getattr(r, 'path', '') != PATH
        ]
        super().tearDown()

    def post(self, body, status, user='contributor', **kwargs):
        headers = self.add_authorization_header(username=user) if user else {}
        headers.update(kwargs.pop('headers', {}))
        return self.app.post_json(PATH, body, headers=headers, status=status, **kwargs)

    def refreshed(self):
        self.session.expire_all()
        return self.session.get(User, self.global_userids['contributor'])

    def test_answer_is_committed(self):
        assert self.post({}, 200).json == {'name': 'renamed'}
        user = self.refreshed()
        assert user.name == 'renamed'
        assert user.ratelimit_remaining == self.limit - 1

    def test_http_error_of_the_view_is_rolled_back(self):
        response = self.post({'outcome': 'http_error'}, 400)
        assert response.json['errors'] == [
            {
                'location': 'body',
                'name': 'Bad Request',
                'description': 'refused by the view',
            }
        ]
        user = self.refreshed()
        # the rate limiting counter too, as with pyramid_tm
        assert user.name == self.name
        assert user.ratelimit_remaining is None

    def test_bug_of_the_view_is_rolled_back(self):
        response = self.post({'outcome': 'bug'}, 500)
        assert response.json['errors'][0]['name'] == 'unexpected error'
        assert self.refreshed().name == self.name

    def test_validation_errors_are_committed(self):
        response = self.post({'outcome': 'invalid'}, 400)
        assert response.json['errors'] == [
            {'location': 'body', 'name': 'outcome', 'description': 'invalid outcome'}
        ]
        user = self.refreshed()
        # the view did not run, the rate limiting counted the request
        assert user.name == self.name
        assert user.ratelimit_remaining == self.limit - 1

    def test_errors_of_the_validators_and_their_status(self):
        response = self.post({'outcome': 'not yours'}, 403)
        assert response.json['errors'] == [
            {'location': 'body', 'name': 'outcome', 'description': 'not yours'}
        ]

    def test_errors_added_by_the_view(self):
        # as Cornice: they are the answer, and they are committed
        response = self.post({'outcome': 'refused by the view'}, 401)
        assert response.json['errors'] == [
            {
                'location': 'body',
                'name': 'outcome',
                'description': 'refused by the view',
            }
        ]
        user = self.refreshed()
        assert user.name == 'renamed'

    def test_client_address(self):
        # as WebOb: the first address of X-Forwarded-For
        response = self.post(
            {'outcome': 'client address'},
            200,
            headers={'X-Forwarded-For': '203.0.113.7, 10.0.0.1'},
        )
        assert response.json == {'client_addr': '203.0.113.7'}

    def test_invalid_json_body(self):
        headers = self.add_authorization_header(username='contributor')
        headers['Content-Type'] = 'application/json'
        response = self.app.post(PATH, '{not json', headers=headers, status=400)
        [error] = response.json['errors']
        assert error['description'].startswith('Invalid JSON: ')

    def test_content_type_and_permission(self):
        headers = self.add_authorization_header(username='contributor')
        headers['Content-Type'] = 'text/plain'
        response = self.app.post(PATH, '{}', headers=headers, status=415)
        assert response.json['errors'][0]['name'] == 'Content-Type'
        response = self.post({}, 403, user=None)
        assert response.json['errors'][0]['description'] == (
            'Unauthorized: _WriteView.collection_post__POST failed permission check'
        )

    @patch('c2corg_api.emails.email_service.EmailService._send_email')
    def test_rate_limit_is_checked_first_and_committed(self, _send_email):
        for _ in range(self.limit):
            self.post({}, 200)
        # over the limit: a 429 before the content type and the permission
        headers = self.add_authorization_header(username='contributor')
        headers['Content-Type'] = 'text/plain'
        response = self.app.post(PATH, '{}', headers=headers, status=429)
        assert response.json['errors'][0]['description'] == 'Rate limit reached'
        user = self.refreshed()
        assert user.ratelimit_remaining == 0
        # the 429 is committed: the window counts as rate limited
        assert user.ratelimit_times == 1
        _send_email.assert_called_once()
