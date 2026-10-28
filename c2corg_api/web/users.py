"""The read routes of the users: account, preferences, follows, blocks."""
# The routes call the view classes of views/ through the adapter of
# web.compat, as the document routes do (#2365).

from email.utils import formatdate
from typing import Annotated

from fastapi import Depends, Request
from fastapi.responses import JSONResponse, Response

from c2corg_api.views.user_account import UserAccountRest
from c2corg_api.views.user_block import UserBlockedAllRest, UserBlockedRest
from c2corg_api.views.user_follow import UserFollowingRest, UserFollowingUserRest
from c2corg_api.views.user_mailinglists import UserMailinglistsRest
from c2corg_api.views.user_preferences import UserFilterPreferencesRest
from c2corg_api.views.validation import validate_id, validate_preferred_lang_param
from c2corg_api.web.auth import CurrentUser, current_user
from c2corg_api.web.compat import serve_view

User = Annotated[CurrentUser | None, Depends(current_user)]

JSON = ['application/json']


def include(app):
    """Add the routes of this module to the FastAPI application."""
    methods = ['GET', 'HEAD']
    app.add_api_route('/users/account', account, methods=methods)
    app.add_api_route('/users/preferences', preferences, methods=methods)
    app.add_api_route('/users/mailinglists', mailinglists, methods=methods)
    app.add_api_route('/users/following', following, methods=methods)
    # a numeric id only, as the document routes (see web.documents)
    app.add_api_route(
        '/users/following-user/{id:int}', is_following_user, methods=methods
    )
    app.add_api_route('/users/blocked', blocked_users, methods=methods)
    app.add_api_route('/users/blocked/{id:int}', is_blocked, methods=methods)


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


def preferences(request: Request, user: User):
    """Return the feed filter preferences of the authenticated user."""
    return serve_view(
        request,
        user,
        [validate_preferred_lang_param],
        UserFilterPreferencesRest,
        permission='authenticated',
    )


def mailinglists(request: Request, user: User):
    """Return the mailing list subscriptions of the authenticated user."""
    return serve_view(
        request, user, [], UserMailinglistsRest, permission='authenticated'
    )


def following(request: Request, user: User):
    """Return the users the authenticated user follows."""
    return serve_view(
        request,
        user,
        [validate_preferred_lang_param],
        UserFollowingRest,
        permission='authenticated',
        content_types=JSON,
    )


def is_following_user(request: Request, user: User):
    """Tell whether the authenticated user follows a user."""
    return serve_view(
        request,
        user,
        [validate_id],
        UserFollowingUserRest,
        permission='authenticated',
        content_types=JSON,
    )


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


def is_blocked(request: Request, user: User):
    """Tell whether a user is blocked."""
    return serve_view(
        request,
        user,
        [validate_id],
        UserBlockedRest,
        permission='moderator',
        content_types=JSON,
    )


# read by the route inventory of the contract tests (routes.txt)
for _endpoint in (account, preferences, mailinglists, following, is_following_user):
    _endpoint.permission = 'authenticated'
for _endpoint in (blocked_users, is_blocked):
    _endpoint.permission = 'moderator'
