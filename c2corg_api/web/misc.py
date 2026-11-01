"""Small routes: coverage lookups, image proxy and list, todo tags, cooker, forum."""
# The routes call the view classes of views/ through the adapter of
# web.compat, as the document routes do (#2365). Their parameters are typed
# (#2512).

from typing import Annotated

from fastapi import Depends, Path, Query, Request

from c2corg_api.views.cooker import CookerRest
from c2corg_api.views.coverage import PolygonCoverage, WaypointCoverageRest
from c2corg_api.views.document_tag import DocumentTaggedRest
from c2corg_api.views.forum import ForumTopicRest
from c2corg_api.views.image import (
    ImageListRest,
    ImageProxyRest,
    validate_extension,
    validate_size,
)
from c2corg_api.views.validation import validate_id
from c2corg_api.web.auth import CurrentUser, current_user
from c2corg_api.web.compat import permission_check, serve_view, typed_values
from c2corg_api.web.documents import include_write
from c2corg_api.web.params import described, finite, natural

User = Annotated[CurrentUser | None, Depends(current_user)]


# the writes: (path, view class, method of the view class), with the checks of
# their Cornice decorators (see web.documents.include_write)
WRITES = [
    ('/cooker', CookerRest, 'post'),
    ('/getpolygoncoverage', PolygonCoverage, 'post'),
    ('/forum/topics', ForumTopicRest, 'collection_post'),
    ('/images/list', ImageListRest, 'collection_post'),
]


def include(app):
    """Add the routes of this module to the FastAPI application."""
    methods = ['GET', 'HEAD']
    # a numeric id only, as the document routes (see web.documents)
    for path, endpoint, tag in (
        ('/getcoverage', coverage_of_a_point, 'coverages'),
        ('/images/proxy/{id:int}', image_proxy, 'images'),
        ('/tags/has/{document_id}', has_todo_tag, 'tags'),
    ):
        app.add_api_route(
            path,
            endpoint,
            methods=methods,
            operation_id=endpoint.__name__,
            tags=[tag],
        )
    for path, view_class, method in WRITES:
        include_write(app, path, 'POST', view_class, method)


def coverage_of_a_point(
    request: Request,
    user: User,
    lon: Annotated[finite('lon'), Query(description='The longitude (WGS 84).')],
    lat: Annotated[finite('lat'), Query(description='The latitude (WGS 84).')],
):
    """Return the type of the coverage containing a point."""
    validated = {'lon': lon, 'lat': lat}
    return serve_view(request, user, [typed_values(validated)], WaypointCoverageRest)


def image_proxy(
    request: Request,
    user: User,
    # described only: the validators of the view check them, since the
    # extension depends on the size
    id: Annotated[
        described({'type': 'integer', 'minimum': 0}),
        Path(description='The image id.'),
    ],
    size: Annotated[
        described({'type': 'string', 'enum': ['SI', 'MI', 'BI']}),
        Query(
            description='A smaller size: `SI`, `MI` or `BI`; the original if not set.'
        ),
    ] = None,
    extension: Annotated[
        described({'type': 'string', 'enum': ['webp', 'avif']}),
        Query(description='Another format, with a size only.'),
    ] = None,
):
    """Redirect to an image file, in a size."""
    validators = [validate_id, validate_size, validate_extension]
    return serve_view(request, user, validators, ImageProxyRest)


def has_todo_tag(
    request: Request,
    user: User,
    _: Annotated[
        None,
        Depends(
            permission_check(
                DocumentTaggedRest, 'get', 'authenticated', ['application/json']
            )
        ),
    ],
    document_id: Annotated[
        natural('document_id'), Path(description='The document id.')
    ],
):
    """Tell whether the authenticated user tagged a document as todo."""
    validated = {'document_id': document_id}
    return serve_view(request, user, [typed_values(validated)], DocumentTaggedRest)


# read by the route inventory of the contract tests (routes.txt)
has_todo_tag.permission = 'authenticated'

for endpoint in (coverage_of_a_point, image_proxy, has_todo_tag):
    # described in the OpenAPI document (see web.openapi)
    endpoint.described = True
