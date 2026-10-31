"""The read routes of the documents: listing, document, info and version."""
# The routes call the view classes of views/ through the adapter of
# web.compat: the logic (caching, ETags, locales, associations, the listing
# filters) and the checks stay the same while the routes move (#2365).

from typing import Annotated

from fastapi import Depends, Path, Query, Request

from c2corg_api.views.document import LIMIT_DEFAULT, LIMIT_MAX
from c2corg_api.web.auth import CurrentUser, current_user
from c2corg_api.web.compat import (
    permission_check,
    serve_view,
    serve_write,
    typed_values,
)
from c2corg_api.web.params import (
    DocumentId,
    Lang,
    Limit,
    Offset,
    PathLang,
    VersionId,
)
from c2corg_api.web.search_parameters import search_filter_parameters

User = Annotated[CurrentUser | None, Depends(current_user)]


def include_document_type(
    app,
    prefix,
    rest,
    version_rest=None,
    info_rest=None,
    listing_permission=None,
    doc_type=None,
):
    """Add the read routes of a document type, served by its view classes."""

    def listing(
        request: Request,
        user: User,
        _: Annotated[
            None, Depends(permission_check(rest, 'collection_get', listing_permission))
        ],
        offset: Annotated[
            Offset | None, Query(description='The first document, from 0.')
        ] = None,
        limit: Annotated[
            Limit | None,
            Query(
                description=f'How many documents: {LIMIT_DEFAULT} by default, '
                f'{LIMIT_MAX} at most. With `offset`, 10000 at most.'
            ),
        ] = None,
        lang: Annotated[
            Lang | None,
            Query(
                alias='pl',
                description='The preferred language: the locale of each document '
                'in this language if it exists, else in the best other one.',
            ),
        ] = None,
        q: Annotated[
            str | None,
            Query(description='Search the titles: in the preferred language if set.'),
        ] = None,
        bbox: Annotated[
            str | None,
            Query(
                description='Only the documents in this box: '
                '`xmin,ymin,xmax,ymax`, in EPSG:3857.'
            ),
        ] = None,
        sort: Annotated[
            str | None,
            Query(
                description='Sort on these fields, comma separated; `-` before a '
                'field for the descending order. With a search only.'
            ),
        ] = None,
    ):
        # `q`, `bbox`, `sort` and the search filters are read by the view
        validated = {'offset': offset, 'limit': limit, 'lang': lang}
        return serve_view(
            request, user, [typed_values(validated)], rest, 'collection_get'
        )

    listing.described = True

    def document(
        request: Request,
        user: User,
        id: DocumentId,
        lang: Annotated[
            Lang | None,
            Query(alias='l', description='Only the locale of this language.'),
        ] = None,
        cook: Annotated[
            Lang | None,
            Query(
                description='Only one locale, in this language if it exists, else '
                'in the best other one, with its Markdown rendered as HTML.'
            ),
        ] = None,
        e: Annotated[
            str,
            Query(
                description='Any other value than 0: the document as stored, for '
                'the edit form, not cached.'
            ),
        ] = '0',
    ):
        # `e` is read by the view
        validated = {'id': id, 'lang': lang, 'cook': cook}
        return serve_view(request, user, [typed_values(validated)], rest)

    # described in the OpenAPI document (see web.openapi)
    document.described = True

    # read by the route inventory of the contract tests (routes.txt)
    listing.permission = listing_permission

    # Only numeric ids: the other paths (/images/list,
    # /routes/update_public_transportation_rating...) are other routes, and an
    # invalid id gets the same 400 from Pyramid.
    methods = ['GET', 'HEAD']
    app.add_api_route(
        f'/{prefix}',
        listing,
        methods=methods,
        operation_id=f'list_{prefix}',
        summary='A page of documents, with their total.',
        description='Without search parameters, the latest documents first. '
        'With any other parameter, a search in Elasticsearch.',
        tags=[prefix],
        openapi_extra={'parameters': search_filter_parameters(doc_type)},
    )
    app.add_api_route(
        f'/{prefix}/{{id:int}}',
        document,
        methods=methods,
        operation_id=f'get_{prefix}_document',
        summary='A document, with its locales and associations.',
        tags=[prefix],
    )

    if info_rest is not None:

        def info(request: Request, user: User, id: DocumentId, lang: PathLang):
            validated = {'id': id, 'lang': lang}
            return serve_view(request, user, [typed_values(validated)], info_rest)

        info.described = True
        app.add_api_route(
            f'/{prefix}/{{id:int}}/{{lang}}/info',
            info,
            methods=methods,
            operation_id=f'get_{prefix}_info',
            summary='The title of a document in a language, for its URL.',
            description='The locale in this language, else in the best other one. '
            'For a redirected document: the id and languages of the document it '
            'redirects to.',
            tags=[prefix],
        )

    if version_rest is not None:

        def version(
            request: Request,
            user: User,
            id: DocumentId,
            lang: PathLang,
            version_id: Annotated[
                VersionId, Path(description='The id of the version.')
            ],
        ):
            validated = {'id': id, 'lang': lang, 'version_id': version_id}
            return serve_view(request, user, [typed_values(validated)], version_rest)

        version.described = True
        path = f'/{prefix}/{{id:int}}/{{lang}}/{{version_id:int}}'
        app.add_api_route(
            path,
            version,
            methods=methods,
            operation_id=f'get_{prefix}_version',
            summary='A version of a document, with the locale of a language.',
            tags=[prefix],
        )


def view_arguments(view_class, method):
    """Return the validators, permission and content types of a view method."""
    # as declared by the @view decorator of the Pyramid view, so that the
    # FastAPI route checks exactly what Pyramid checked
    [arguments] = getattr(view_class, method).__views__
    content_type = arguments.get('content_type')
    if isinstance(content_type, str):
        content_type = [content_type]
    return arguments.get('validators', []), arguments.get('permission'), content_type


def include_write(app, path, http_method, view_class, method):
    """Add a write route served by a method of a Pyramid view class."""
    validators, permission, content_types = view_arguments(view_class, method)

    async def endpoint(request: Request, user: User):
        return await serve_write(
            request, user, validators, view_class, method, permission, content_types
        )

    # read by the route inventory of the contract tests (routes.txt)
    endpoint.permission = permission
    app.add_api_route(path, endpoint, methods=[http_method])


def include_document_writes(app, prefix, rest, create=True):
    """Add the write routes of a document type: creation and update."""
    if create:
        include_write(app, f'/{prefix}', 'POST', rest, 'collection_post')
    # a numeric id only, as the read routes
    include_write(app, f'/{prefix}/{{id:int}}', 'PUT', rest, 'put')


def include(app):
    """Add the document routes moved to FastAPI."""
    from c2corg_api.models.common.document_types import (
        AREA_TYPE,
        ARTICLE_TYPE,
        BOOK_TYPE,
        COVERAGE_TYPE,
        IMAGE_TYPE,
        MAP_TYPE,
        OUTING_TYPE,
        ROUTE_TYPE,
        USERPROFILE_TYPE,
        WAYPOINT_TYPE,
        XREPORT_TYPE,
    )
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

    include_document_type(
        app, 'books', BookRest, BooksVersionRest, BooksInfoRest, doc_type=BOOK_TYPE
    )
    include_document_type(
        app,
        'articles',
        ArticleRest,
        ArticlesVersionRest,
        ArticlesInfoRest,
        doc_type=ARTICLE_TYPE,
    )
    include_document_type(
        app, 'areas', AreaRest, AreaVersionRest, AreaInfoRest, doc_type=AREA_TYPE
    )
    # maps have no version route, coverages neither version nor info
    include_document_type(
        app, 'maps', TopoMapRest, info_rest=TopoMapInfoRest, doc_type=MAP_TYPE
    )
    include_document_type(app, 'coverages', CoverageRest, doc_type=COVERAGE_TYPE)
    # the image proxy (/images/proxy/{id}) and /images/list stay on Pyramid
    include_document_type(
        app, 'images', ImageRest, ImageVersionRest, ImageInfoRest, doc_type=IMAGE_TYPE
    )
    # the personal fields of an xreport are for its author and the moderators
    include_document_type(
        app,
        'xreports',
        XreportRest,
        XreportVersionRest,
        XreportInfoRest,
        doc_type=XREPORT_TYPE,
    )
    include_document_type(
        app,
        'outings',
        OutingRest,
        OutingVersionRest,
        OutingInfoRest,
        doc_type=OUTING_TYPE,
    )
    # /reachableroutes and /routes/update_public_transportation_rating stay on
    # Pyramid
    include_document_type(
        app, 'routes', RouteRest, RouteVersionRest, RouteInfoRest, doc_type=ROUTE_TYPE
    )
    # /reachablewaypoints, /waypoints/{id}/stopareas, /waypoints/{id}/isReachable
    # and /waypoints_stopareas/... stay on Pyramid
    include_document_type(
        app,
        'waypoints',
        WaypointRest,
        WaypointVersionRest,
        WaypointInfoRest,
        doc_type=WAYPOINT_TYPE,
    )
    # the listing of the profiles is for the authenticated users, and a private
    # profile shows only the user name to the others; no version route
    include_document_type(
        app,
        'profiles',
        UserProfileRest,
        info_rest=UserProfileInfoRest,
        listing_permission='authenticated',
        doc_type=USERPROFILE_TYPE,
    )
    # a GET that writes (the ratings of all the routes, for the moderators):
    # served as a write, so that it is committed
    from c2corg_api.views.route import RoutePublicTransportationRatingRest

    for http_method in ('GET', 'HEAD'):
        include_write(
            app,
            '/routes/update_public_transportation_rating',
            http_method,
            RoutePublicTransportationRatingRest,
            'get',
        )
    # the writes moved to FastAPI
    include_document_writes(app, 'books', BookRest)
    include_document_writes(app, 'articles', ArticleRest)
    include_document_writes(app, 'areas', AreaRest)
    include_document_writes(app, 'maps', TopoMapRest)
    include_document_writes(app, 'coverages', CoverageRest)
    include_document_writes(app, 'xreports', XreportRest)
    # the image proxy and /images/list (POST) stay on Pyramid
    include_document_writes(app, 'images', ImageRest)
    # a profile is created with its user: no creation route
    include_document_writes(app, 'profiles', UserProfileRest, create=False)
    include_document_writes(app, 'outings', OutingRest)
    include_document_writes(app, 'routes', RouteRest)
    include_document_writes(app, 'waypoints', WaypointRest)
