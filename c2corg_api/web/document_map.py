"""The map overlays of outings and routes: their density and their tracks."""
# The routes call the functions of views/document_map.py through
# web.handlers, as the other read routes do. The search filters of the
# documents listing (act, date, r, w, a, ...) are read from the query by the
# view: they are described in the OpenAPI document, not declared one by one.

from typing import Annotated

from fastapi import Depends, Query, Request

from c2corg_api.models.outing import OUTING_TYPE
from c2corg_api.models.route import ROUTE_TYPE
from c2corg_api.views.document_map import (
    read_outings_heatmap,
    read_outings_tracks,
    read_routes_heatmap,
    read_routes_tracks,
)
from c2corg_api.views.validation import (
    validate_bbox,
    validate_preferred_lang_param,
    validate_zoom,
)
from c2corg_api.web.auth import CurrentUser, current_user
from c2corg_api.web.handlers import serve_read
from c2corg_api.web.params import Lang, described
from c2corg_api.web.search_parameters import search_filter_parameters

User = Annotated[CurrentUser | None, Depends(current_user)]
# checked by the validators of views/validation.py
Bbox = Annotated[
    described({'type': 'string'}),
    Query(description='The box: `xmin,ymin,xmax,ymax`, in EPSG:3857.'),
]
Zoom = Annotated[
    described({'type': 'integer'}),
    Query(
        description='The zoom level of the map: it sets the size of the cells '
        'of the density.'
    ),
]
PreferredLang = Annotated[
    Lang | None,
    Query(
        alias='pl',
        description='The locale of each document in this language if it exists, '
        'else in the best other one.',
    ),
]

FILTERS = 'The search filters of the documents listing apply as well.'


def include(app):
    """Add the routes of this module to the FastAPI application."""
    methods = ['GET', 'HEAD']
    for prefix, doc_type, heatmap, tracks in (
        ('outings', OUTING_TYPE, outings_heatmap, outings_tracks),
        ('routes', ROUTE_TYPE, routes_heatmap, routes_tracks),
    ):
        parameters = search_filter_parameters(doc_type)
        app.add_api_route(
            f'/{prefix}/map/heatmap',
            heatmap,
            methods=methods,
            operation_id=heatmap.__name__,
            summary=f'The density of the {prefix} in a box.',
            description='Buckets `{x, y, count}` (EPSG:3857) of a grid whose '
            f'cells depend on the zoom, for a heatmap. {FILTERS}',
            tags=[prefix],
            openapi_extra={'parameters': parameters},
        )
        app.add_api_route(
            f'/{prefix}/map/tracks',
            tracks,
            methods=methods,
            operation_id=tracks.__name__,
            summary=f'The tracks of the {prefix} in a box.',
            description='The tracks (GeoJSON) of the documents crossing the box. '
            'With more than 100 of them the answer is empty and `truncated` is '
            f'set. {FILTERS} `ids` restricts the answer to some documents.',
            tags=[prefix],
            openapi_extra={'parameters': parameters},
        )


def outings_heatmap(request: Request, user: User, bbox: Bbox = None, zoom: Zoom = None):
    """Return the density of the outings in a box."""
    return serve_read(
        request, user, [validate_bbox, validate_zoom], read_outings_heatmap
    )


def outings_tracks(
    request: Request, user: User, bbox: Bbox = None, lang: PreferredLang = None
):
    """Return the tracks of the outings in a box."""
    return serve_read(
        request,
        user,
        [validate_bbox, validate_preferred_lang_param],
        read_outings_tracks,
    )


def routes_heatmap(request: Request, user: User, bbox: Bbox = None, zoom: Zoom = None):
    """Return the density of the routes in a box."""
    return serve_read(
        request, user, [validate_bbox, validate_zoom], read_routes_heatmap
    )


def routes_tracks(
    request: Request, user: User, bbox: Bbox = None, lang: PreferredLang = None
):
    """Return the tracks of the routes in a box."""
    return serve_read(
        request,
        user,
        [validate_bbox, validate_preferred_lang_param],
        read_routes_tracks,
    )
