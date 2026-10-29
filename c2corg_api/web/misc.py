"""Small routes: coverage lookups, image proxy and list, todo tags, cooker, forum."""
# The routes call the view classes of views/ through the adapter of
# web.compat, as the document routes do (#2365).

from typing import Annotated

from fastapi import Depends, Request

from c2corg_api.views.cooker import CookerRest
from c2corg_api.views.coverage import (
    PolygonCoverage,
    WaypointCoverageRest,
    validate_lon_lat,
)
from c2corg_api.views.document_tag import DocumentTaggedRest, validate_document_id
from c2corg_api.views.forum import ForumTopicRest
from c2corg_api.views.image import (
    ImageListRest,
    ImageProxyRest,
    validate_extension,
    validate_size,
)
from c2corg_api.views.validation import validate_id
from c2corg_api.web.auth import CurrentUser, current_user
from c2corg_api.web.compat import serve_view
from c2corg_api.web.documents import include_write

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
    app.add_api_route('/getcoverage', coverage_of_a_point, methods=methods)
    # a numeric id only, as the document routes (see web.documents)
    app.add_api_route('/images/proxy/{id:int}', image_proxy, methods=methods)
    app.add_api_route('/tags/has/{document_id}', has_todo_tag, methods=methods)
    for path, view_class, method in WRITES:
        include_write(app, path, 'POST', view_class, method)


def coverage_of_a_point(request: Request, user: User):
    """Return the type of the coverage containing a point."""
    return serve_view(request, user, [validate_lon_lat], WaypointCoverageRest)


def image_proxy(request: Request, user: User):
    """Redirect to an image file, in a size."""
    validators = [validate_id, validate_size, validate_extension]
    return serve_view(request, user, validators, ImageProxyRest)


def has_todo_tag(request: Request, user: User):
    """Tell whether the authenticated user tagged a document as todo."""
    return serve_view(
        request,
        user,
        [validate_document_id],
        DocumentTaggedRest,
        permission='authenticated',
        content_types=['application/json'],
    )


# read by the route inventory of the contract tests (routes.txt)
has_todo_tag.permission = 'authenticated'
