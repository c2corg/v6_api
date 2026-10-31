"""The feeds: of the homepage, of the authenticated user, of a user profile."""
# The routes call the view classes of views/ through the adapter of
# web.compat, as the document routes do (#2365). Their parameters are typed
# (#2512).

from typing import Annotated

from fastapi import Depends, Query, Request

from c2corg_api.views.feed import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    FeedRest,
    PersonalFeedRest,
    ProfileFeedRest,
)
from c2corg_api.web.auth import CurrentUser, current_user
from c2corg_api.web.compat import permission_check, serve_view, typed_values
from c2corg_api.web.params import FeedToken, Lang, Limit, integer

User = Annotated[CurrentUser | None, Depends(current_user)]
PreferredLang = Annotated[
    Lang | None,
    Query(
        alias='pl',
        description='Only the locale of this language, if the document has one; '
        'else all the locales.',
    ),
]
PageLimit = Annotated[
    Limit | None,
    Query(
        description=f'How many changes: {DEFAULT_PAGE_LIMIT} by default, '
        f'{MAX_PAGE_LIMIT} at most.'
    ),
]
Token = Annotated[
    FeedToken | None,
    Query(description='The `pagination_token` of the previous page.'),
]


def include(app):
    """Add the routes of this module to the FastAPI application."""
    methods = ['GET', 'HEAD']
    for path, endpoint in (
        ('/feed', feed),
        ('/personal-feed', personal_feed),
        ('/profile-feed', profile_feed),
    ):
        app.add_api_route(
            path,
            endpoint,
            methods=methods,
            operation_id=endpoint.__name__,
            tags=['feeds'],
        )


def _validated(lang, limit, token, **others):
    # the token is `{id},{date and time}`: the views read both parts
    token_id, token_time = token if token is not None else (None, None)
    return {
        'lang': lang,
        'limit': limit,
        'token_id': token_id,
        'token_time': token_time,
        **others,
    }


def feed(
    request: Request,
    user: User,
    lang: PreferredLang = None,
    limit: PageLimit = None,
    token: Token = None,
):
    """Return the public feed of the homepage."""
    validated = _validated(lang, limit, token)
    return serve_view(request, user, [typed_values(validated)], FeedRest)


def personal_feed(
    request: Request,
    user: User,
    _: Annotated[
        None, Depends(permission_check(PersonalFeedRest, 'get', 'authenticated'))
    ],
    lang: PreferredLang = None,
    limit: PageLimit = None,
    token: Token = None,
):
    """Return the feed of the authenticated user."""
    validated = _validated(lang, limit, token)
    return serve_view(request, user, [typed_values(validated)], PersonalFeedRest)


# read by the route inventory of the contract tests (routes.txt)
personal_feed.permission = 'authenticated'


def profile_feed(
    request: Request,
    user: User,
    *,
    lang: PreferredLang = None,
    limit: PageLimit = None,
    token: Token = None,
    # last: its error comes after those of the others, as its validator did
    u: Annotated[integer('u'), Query(description='The user (id).')],
):
    """Return the feed of a user profile (if public, or for authenticated users)."""
    validated = _validated(lang, limit, token, u=u)
    return serve_view(request, user, [typed_values(validated)], ProfileFeedRest)


for endpoint in (feed, personal_feed, profile_feed):
    # described in the OpenAPI document (see web.openapi)
    endpoint.described = True
