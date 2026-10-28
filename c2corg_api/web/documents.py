"""The read routes of the documents: listing, document, info and version."""
# The routes call the view classes of views/ through the adapter of
# web.compat: the logic (caching, ETags, locales, associations, the listing
# filters) and the checks stay the same while the routes move (#2365).

from typing import Annotated

from fastapi import Depends, Request

from c2corg_api.views.validation import (
    validate_cook_param,
    validate_id,
    validate_lang,
    validate_lang_param,
    validate_pagination,
    validate_preferred_lang_param,
    validate_version_id,
)
from c2corg_api.web.auth import CurrentUser, current_user
from c2corg_api.web.compat import serve_view, serve_write

User = Annotated[CurrentUser | None, Depends(current_user)]


def include_document_type(
    app, prefix, rest, version_rest=None, info_rest=None, listing_permission=None
):
    """Add the read routes of a document type, served by its view classes."""

    def listing(request: Request, user: User):
        return serve_view(
            request,
            user,
            [validate_pagination, validate_preferred_lang_param],
            rest,
            'collection_get',
            permission=listing_permission,
        )

    def document(request: Request, user: User):
        return serve_view(
            request,
            user,
            [validate_id, validate_lang_param, validate_cook_param],
            rest,
        )

    # read by the route inventory of the contract tests (routes.txt)
    listing.permission = listing_permission

    # Only numeric ids: the other paths (/images/list,
    # /routes/update_public_transportation_rating...) are other routes, and an
    # invalid id gets the same 400 from Pyramid.
    methods = ['GET', 'HEAD']
    app.add_api_route(f'/{prefix}', listing, methods=methods)
    app.add_api_route(f'/{prefix}/{{id:int}}', document, methods=methods)

    if info_rest is not None:

        def info(request: Request, user: User):
            return serve_view(request, user, [validate_id, validate_lang], info_rest)

        app.add_api_route(f'/{prefix}/{{id:int}}/{{lang}}/info', info, methods=methods)

    if version_rest is not None:

        def version(request: Request, user: User):
            return serve_view(
                request,
                user,
                [validate_id, validate_lang, validate_version_id],
                version_rest,
            )

        path = f'/{prefix}/{{id:int}}/{{lang}}/{{version_id:int}}'
        app.add_api_route(path, version, methods=methods)


def cornice_view(view_class, method):
    """Return the validators, permission and content types of a Cornice view."""
    # as declared by the @view decorator of the Pyramid view, so that the
    # FastAPI route checks exactly what Pyramid checked
    [arguments] = getattr(view_class, method).__views__
    content_type = arguments.get('content_type')
    if isinstance(content_type, str):
        content_type = [content_type]
    return arguments.get('validators', []), arguments.get('permission'), content_type


def include_document_writes(app, prefix, rest):
    """Add the write routes of a document type: creation and update."""

    def write_route(path, http_method, method):
        validators, permission, content_types = cornice_view(rest, method)

        async def endpoint(request: Request, user: User):
            return await serve_write(
                request, user, validators, rest, method, permission, content_types
            )

        # read by the route inventory of the contract tests (routes.txt)
        endpoint.permission = permission
        app.add_api_route(path, endpoint, methods=[http_method])

    write_route(f'/{prefix}', 'POST', 'collection_post')
    # a numeric id only, as the read routes
    write_route(f'/{prefix}/{{id:int}}', 'PUT', 'put')


def include(app):
    """Add the document routes moved to FastAPI."""
    from c2corg_api.views.area import AreaInfoRest, AreaRest, AreaVersionRest
    from c2corg_api.views.article import (
        ArticleRest,
        ArticlesInfoRest,
        ArticlesVersionRest,
    )
    from c2corg_api.views.book import BookRest, BooksInfoRest, BooksVersionRest
    from c2corg_api.views.coverage import CoverageRest
    from c2corg_api.views.image import ImageInfoRest, ImageRest, ImageVersionRest
    from c2corg_api.views.outing import OutingInfoRest, OutingRest, OutingVersionRest
    from c2corg_api.views.route import RouteInfoRest, RouteRest, RouteVersionRest
    from c2corg_api.views.topo_map import TopoMapInfoRest, TopoMapRest
    from c2corg_api.views.user_profile import UserProfileInfoRest, UserProfileRest
    from c2corg_api.views.waypoint import (
        WaypointInfoRest,
        WaypointRest,
        WaypointVersionRest,
    )
    from c2corg_api.views.xreport import (
        XreportInfoRest,
        XreportRest,
        XreportVersionRest,
    )

    include_document_type(app, 'books', BookRest, BooksVersionRest, BooksInfoRest)
    include_document_type(
        app, 'articles', ArticleRest, ArticlesVersionRest, ArticlesInfoRest
    )
    include_document_type(app, 'areas', AreaRest, AreaVersionRest, AreaInfoRest)
    # maps have no version route, coverages neither version nor info
    include_document_type(app, 'maps', TopoMapRest, info_rest=TopoMapInfoRest)
    include_document_type(app, 'coverages', CoverageRest)
    # the image proxy (/images/proxy/{id}) and /images/list stay on Pyramid
    include_document_type(app, 'images', ImageRest, ImageVersionRest, ImageInfoRest)
    # the personal fields of an xreport are for its author and the moderators
    include_document_type(
        app, 'xreports', XreportRest, XreportVersionRest, XreportInfoRest
    )
    include_document_type(app, 'outings', OutingRest, OutingVersionRest, OutingInfoRest)
    # /reachableroutes and /routes/update_public_transportation_rating stay on
    # Pyramid
    include_document_type(app, 'routes', RouteRest, RouteVersionRest, RouteInfoRest)
    # /reachablewaypoints, /waypoints/{id}/stopareas, /waypoints/{id}/isReachable
    # and /waypoints_stopareas/... stay on Pyramid
    include_document_type(
        app, 'waypoints', WaypointRest, WaypointVersionRest, WaypointInfoRest
    )
    # the listing of the profiles is for the authenticated users, and a private
    # profile shows only the user name to the others; no version route
    include_document_type(
        app,
        'profiles',
        UserProfileRest,
        info_rest=UserProfileInfoRest,
        listing_permission='authenticated',
    )
    # the writes moved to FastAPI
    include_document_writes(app, 'books', BookRest)
