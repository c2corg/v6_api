"""The feeds: of the homepage, of the authenticated user, of a user profile."""
# The routes call the view classes of views/ through the adapter of
# web.compat, as the document routes do (#2365).

from typing import Annotated

from fastapi import Depends, Request

from c2corg_api.views.feed import FeedRest, PersonalFeedRest, ProfileFeedRest
from c2corg_api.views.validation import (
    validate_preferred_lang_param,
    validate_token_pagination,
    validate_user_id,
)
from c2corg_api.web.auth import CurrentUser, current_user
from c2corg_api.web.compat import serve_view

User = Annotated[CurrentUser | None, Depends(current_user)]

VALIDATORS = [validate_preferred_lang_param, validate_token_pagination]


def include(app):
    """Add the routes of this module to the FastAPI application."""
    methods = ['GET', 'HEAD']
    app.add_api_route('/feed', feed, methods=methods)
    app.add_api_route('/personal-feed', personal_feed, methods=methods)
    app.add_api_route('/profile-feed', profile_feed, methods=methods)


def feed(request: Request, user: User):
    """Return the public feed of the homepage."""
    return serve_view(request, user, VALIDATORS, FeedRest)


def personal_feed(request: Request, user: User):
    """Return the feed of the authenticated user."""
    return serve_view(
        request, user, VALIDATORS, PersonalFeedRest, permission='authenticated'
    )


# read by the route inventory of the contract tests (routes.txt)
personal_feed.permission = 'authenticated'


def profile_feed(request: Request, user: User):
    """Return the feed of a user profile (if public, or for authenticated users)."""
    return serve_view(request, user, [*VALIDATORS, validate_user_id], ProfileFeedRest)
