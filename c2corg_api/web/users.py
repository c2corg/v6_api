"""The routes of the users: account, preferences, follows, blocks, login, SSO..."""
# The routes call the view classes of views/ through the adapter of
# web.compat, as the document routes do (#2365).

from email.utils import formatdate
from typing import Annotated

from fastapi import Depends, Path, Query, Request
from fastapi.responses import JSONResponse, Response

from c2corg_api.views.sso import sso_login, sso_sync
from c2corg_api.views.user import (
    discourse_redirect,
    login_user,
    logout_user,
    register_user,
    renew_login,
    request_password_change,
    validate_change_email,
    validate_new_password,
    validate_register_email,
)
from c2corg_api.views.user_account import (
    UserAccountRest,
    update_account,
    update_preferred_language,
)
from c2corg_api.views.user_block import UserBlockedAllRest, UserBlockedRest
from c2corg_api.views.user_follow import UserFollowingRest, UserFollowingUserRest
from c2corg_api.views.user_mailinglists import UserMailinglistsRest
from c2corg_api.views.user_preferences import UserFilterPreferencesRest
from c2corg_api.web.auth import CurrentUser, current_user
from c2corg_api.web.compat import permission_check, serve_view, typed_values
from c2corg_api.web.documents import handler_arguments, include_handler_write
from c2corg_api.web.params import Id, Lang

User = Annotated[CurrentUser | None, Depends(current_user)]

JSON = ['application/json']


# the writes: (path, function), POST, with the checks of the function's
# decorator (see web.documents.include_document_writes); the tokens and the
# Discourse SSO are the same as with Pyramid
WRITES = [
    ('/users/register', register_user),
    ('/users/validate_register_email/{nonce}', validate_register_email),
    ('/users/request_password_change', request_password_change),
    ('/users/validate_new_password/{nonce}', validate_new_password),
    ('/users/validate_change_email/{nonce}', validate_change_email),
    ('/users/login', login_user),
    ('/users/renew', renew_login),
    ('/users/logout', logout_user),
    ('/users/account', update_account),
    ('/users/update_preferred_language', update_preferred_language),
    ('/users/discourse-redirect', discourse_redirect),
    ('/sso_sync', sso_sync),
    ('/sso_login', sso_login),
]


def include(app):
    """Add the routes of this module to the FastAPI application."""
    methods = ['GET', 'HEAD']
    # a numeric id only, as the document routes (see web.documents)
    for path, endpoint in (
        ('/users/account', account),
        ('/users/preferences', preferences),
        ('/users/mailinglists', mailinglists),
        ('/users/following', following),
        ('/users/following-user/{id:int}', is_following_user),
        ('/users/blocked', blocked_users),
        ('/users/blocked/{id:int}', is_blocked),
    ):
        app.add_api_route(
            path,
            endpoint,
            methods=methods,
            operation_id=f'user_{endpoint.__name__}',
            tags=['users'],
        )
    for path, function in WRITES:
        include_handler_write(app, path, 'POST', function, *handler_arguments(function))


def account(request: Request, user: User):
    """Return the account of the authenticated user."""
    response = serve_view(
        request, user, [], UserAccountRest, permission='authenticated'
    )
    if isinstance(response, Response):
        return response
    # http_cache=0 of the Pyramid view
    now = formatdate(usegmt=True)
    headers = {
        'Cache-Control': 'max-age=0, must-revalidate, no-cache, no-store',
        'Expires': now,
        'Last-Modified': now,
        'Pragma': 'no-cache',
    }
    return JSONResponse(response, headers=headers)


def _checks(view_class, permission, content_types=None):
    # the content type and the permission are checked before the parameters,
    # as Cornice and Pyramid did
    check = permission_check(view_class, 'get', permission, content_types)
    return Annotated[None, Depends(check)]


PreferredLang = Annotated[
    Lang | None,
    Query(
        alias='pl',
        description='The locale of each document in this language if it exists, '
        'else in the best other one.',
    ),
]
UserId = Annotated[Id, Path(description='The user id.')]


def preferences(
    request: Request,
    user: User,
    _: _checks(UserFilterPreferencesRest, 'authenticated'),
    lang: PreferredLang = None,
):
    """Return the feed filter preferences of the authenticated user."""
    validated = {'lang': lang}
    view = UserFilterPreferencesRest
    return serve_view(request, user, [typed_values(validated)], view)


def mailinglists(request: Request, user: User):
    """Return the mailing list subscriptions of the authenticated user."""
    return serve_view(
        request, user, [], UserMailinglistsRest, permission='authenticated'
    )


def following(
    request: Request,
    user: User,
    _: _checks(UserFollowingRest, 'authenticated', JSON),
    lang: Annotated[
        Lang | None, Query(alias='pl', description='Checked, not used.')
    ] = None,
):
    """Return the users the authenticated user follows."""
    validated = {'lang': lang}
    return serve_view(request, user, [typed_values(validated)], UserFollowingRest)


def is_following_user(
    request: Request,
    user: User,
    _: _checks(UserFollowingUserRest, 'authenticated', JSON),
    id: UserId,
):
    """Tell whether the authenticated user follows a user."""
    validated = {'id': id}
    view = UserFollowingUserRest
    return serve_view(request, user, [typed_values(validated)], view)


def blocked_users(request: Request, user: User):
    """Return the blocked users."""
    return serve_view(
        request,
        user,
        [],
        UserBlockedAllRest,
        permission='moderator',
        content_types=JSON,
    )


def is_blocked(
    request: Request,
    user: User,
    _: _checks(UserBlockedRest, 'moderator', JSON),
    id: UserId,
):
    """Tell whether a user is blocked."""
    validated = {'id': id}
    return serve_view(request, user, [typed_values(validated)], UserBlockedRest)


# read by the route inventory of the contract tests (routes.txt)
for _endpoint in (account, preferences, mailinglists, following, is_following_user):
    _endpoint.permission = 'authenticated'
for _endpoint in (blocked_users, is_blocked):
    _endpoint.permission = 'moderator'
for _endpoint in (
    account,
    preferences,
    mailinglists,
    following,
    is_following_user,
    blocked_users,
    is_blocked,
):
    # described in the OpenAPI document (see web.openapi)
    _endpoint.described = True
