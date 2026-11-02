import logging
import math

from cornice.resource import resource, view

from c2corg_api.ext.wkb import geojson_from_wkbelement
from c2corg_api.models.document_map_queries import get_locales_for_documents, get_tracks
from c2corg_api.models.outing import OUTING_TYPE, Outing, OutingLocale
from c2corg_api.models.route import ROUTE_TYPE, Route, RouteLocale
from c2corg_api.search.search_filters import build_query
from c2corg_api.security.acl import ACLDefault
from c2corg_api.views import cors_policy, get_best_locale
from c2corg_api.views.validation import (
    validate_bbox,
    validate_preferred_lang_param,
    validate_zoom,
)

log = logging.getLogger(__name__)

# above this number of individual tracks in a bbox, the tracks endpoints
# report "too many results" instead of returning a partial list
TRACKS_LIMIT_MAX = 100

# maximum number of candidate documents asked to ElasticSearch for the
# tracks endpoints (the bbox is then applied again on the actual tracks)
TRACKS_CANDIDATES_MAX = 1000

# `geohash_grid` aggregations allow at most 10000 buckets (the most populated
# ones are kept)
HEATMAP_BUCKETS_MAX = 10000

# geohash length (cell size) used for the heatmap, indexed by the lowest map
# zoom level it applies to: ~1250km, 156km, 39km, 4.9km, 1.2km and 150m
# cells. Meant to give roughly 100 cells across a viewport.
HEATMAP_PRECISION_BY_MIN_ZOOM = ((0, 2), (3, 3), (5, 4), (8, 5), (11, 6), (14, 7))

# radius of the sphere used by EPSG:3857 (meters)
WEB_MERCATOR_RADIUS = 6378137

GEOHASH_BASE32 = '0123456789bcdefghjkmnpqrstuvwxyz'

# url parameters that are not search filters
NON_FILTER_PARAMS = ('zoom',)


def _search_params(request):
    """Return the url parameters handled as search filters.

    Returns the url parameters handled as search filters: the same ones
    as the documents listing, so that the map layers match a search made
    from the listing.
    """
    return {
        key: request.GET.get(key) for key in request.GET if key not in NON_FILTER_PARAMS
    }


def _expanded_bbox(bbox, ratio=0.5):
    """Grows the bbox by `ratio` of its size on each side.

    The search index only knows one point per document, whereas a track can extend far
    away from this point.
    """
    xmin, ymin, xmax, ymax = bbox
    dx = (xmax - xmin) * ratio
    dy = (ymax - ymin) * ratio
    return xmin - dx, ymin - dy, xmax + dx, ymax + dy


def _bbox_param(bbox):
    return ','.join(str(value) for value in bbox)


def _heatmap_precision(zoom):
    precision = HEATMAP_PRECISION_BY_MIN_ZOOM[0][1]
    for min_zoom, candidate in HEATMAP_PRECISION_BY_MIN_ZOOM:
        if zoom >= min_zoom:
            precision = candidate
    return precision


def _geohash_center(geohash):
    """Return the `(lon, lat)` center of a geohash cell."""
    lat_range = [-90.0, 90.0]
    lon_range = [-180.0, 180.0]
    is_lon = True
    for char in geohash:
        value = GEOHASH_BASE32.index(char)
        for bit in (16, 8, 4, 2, 1):
            current = lon_range if is_lon else lat_range
            middle = (current[0] + current[1]) / 2
            current[0 if value & bit else 1] = middle
            is_lon = not is_lon
    return (sum(lon_range) / 2, sum(lat_range) / 2)


def _lon_lat_to_3857(lon, lat):
    x = math.radians(lon) * WEB_MERCATOR_RADIUS
    y = WEB_MERCATOR_RADIUS * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    return x, y


def _build_search(doc_type, params, bbox, meta_params):
    """Build the search query of the documents matching the filters.

    Builds the search query of the documents matching the filters in the
    given bbox. On top of the filters of the documents listing, an `ids=1,2`
    parameter restricts the result to the given documents (an empty list
    matches nothing).
    """
    params = dict(params, bbox=_bbox_param(bbox))
    ids = params.pop('ids', None)

    search = build_query(params, meta_params, doc_type)
    if ids is not None:
        search = search.filter(
            'ids', values=[value for value in ids.split(',') if value.isdigit()]
        )
    return search


def get_heatmap(doc_type, params, bbox, zoom):
    """Return the density buckets of the documents matching the filters.

    Returns the density buckets (`{x, y, count}` in EPSG:3857) of the
    documents matching the search filters in the given bbox.
    """
    search = _build_search(doc_type, params, bbox, {'limit': 0, 'offset': 0})
    search.aggs.bucket(
        'density',
        'geohash_grid',
        field='geom',
        precision=_heatmap_precision(zoom),
        size=HEATMAP_BUCKETS_MAX,
    )
    response = search.execute()

    buckets = []
    for bucket in response.aggregations.density.buckets:
        x, y = _lon_lat_to_3857(*_geohash_center(bucket.key))
        buckets.append({'x': x, 'y': y, 'count': bucket.doc_count})

    return {'buckets': buckets}


def get_track_candidates(doc_type, params, bbox):
    """Return the documents matching the filters around a bbox.

    Returns `(document_ids, truncated)` for the documents matching the
    search filters around the given bbox. `truncated` is set when there
    are more candidates than what is asked to the search index.
    """
    search = _build_search(
        doc_type,
        params,
        _expanded_bbox(bbox),
        {'limit': TRACKS_CANDIDATES_MAX, 'offset': 0},
    )
    response = search.execute()
    document_ids = [int(doc.meta.id) for doc in response]
    return document_ids, response.hits.total > len(document_ids)


def _titles_by_document_id(locale_model, document_ids, lang):
    locales_by_document = {}
    for locale in get_locales_for_documents(locale_model, document_ids):
        locales_by_document.setdefault(locale.document_id, {})[locale.lang] = locale

    titles = {}
    for document_id, available_locales in locales_by_document.items():
        best_locale = get_best_locale(available_locales, lang)
        if best_locale:
            title_prefix = getattr(best_locale, 'title_prefix', None)
            titles[document_id] = (
                f'{title_prefix} : {best_locale.title}'
                if title_prefix
                else best_locale.title
            )
    return titles


def get_tracks_response(doc_type, model, locale_model, request):
    params = _search_params(request)
    bbox = request.validated['bbox']
    lang = request.validated.get('lang')

    document_ids, truncated = get_track_candidates(doc_type, params, bbox)
    if truncated:
        return {'documents': [], 'truncated': True}

    rows = get_tracks(model, document_ids, bbox, TRACKS_LIMIT_MAX)
    if len(rows) > TRACKS_LIMIT_MAX:
        return {'documents': [], 'truncated': True}

    titles = _titles_by_document_id(
        locale_model, [row.document_id for row in rows], lang
    )

    return {
        'documents': [
            {
                'document_id': row.document_id,
                'type': doc_type,
                'title': titles.get(row.document_id),
                'geometry': {'geom_detail': geojson_from_wkbelement(row.geom_detail)},
            }
            for row in rows
        ],
        'truncated': False,
    }


def get_heatmap_response(doc_type, request):
    return get_heatmap(
        doc_type,
        _search_params(request),
        request.validated['bbox'],
        request.validated['zoom'],
    )


# The heatmap resources return a grid of density buckets for the given bbox,
# meant to feed a heatmap layer at low/medium map zoom levels.
#
#   `GET` `/{outings,routes}/map/heatmap?bbox=...&zoom=...[&<filters>]`
#
#   `bbox=xmin,ymin,xmax,ymax` (required, EPSG:3857)
#
#   `zoom=...` (required): the current map zoom level. Used server-side to
#   pick a grid cell size, so that a client cannot request an arbitrarily
#   fine-grained aggregation over a large area.
#
#   Any filter accepted by the documents listing (`act`, `r`, `date`, ...)
#   restricts the heatmap accordingly.
#
#   Response: `{"buckets": [{"x":.., "y":.., "count":..}]}`
#   Coordinates are in EPSG:3857, matching the map's projection.
#
# The tracks resources return individual tracks for the given bbox, meant to
# feed a vector layer at high map zoom levels (once the number of documents
# in the viewport is bounded).
#
#   `GET` `/{outings,routes}/map/tracks?bbox=...[&pl=...][&<filters>]`
#
#   Response: `{"documents": [{"document_id":.., "type": "o"|"r",
#   "title":.., "geometry": {"geom_detail": "<geojson>"}}],
#   "truncated": false}`
#
#   If more than `TRACKS_LIMIT_MAX` documents intersect the bbox, an empty,
#   `"truncated": true` response is returned instead of a silently
#   incomplete list, so that the frontend can prompt the user to zoom in.


@resource(path='/outings/map/heatmap', cors_policy=cors_policy)
class OutingsHeatmapRest(ACLDefault):
    @view(validators=[validate_bbox, validate_zoom])
    def get(self):
        return get_heatmap_response(OUTING_TYPE, self.request)


@resource(path='/outings/map/tracks', cors_policy=cors_policy)
class OutingsTracksRest(ACLDefault):
    @view(validators=[validate_bbox, validate_preferred_lang_param])
    def get(self):
        return get_tracks_response(OUTING_TYPE, Outing, OutingLocale, self.request)


@resource(path='/routes/map/heatmap', cors_policy=cors_policy)
class RoutesHeatmapRest(ACLDefault):
    @view(validators=[validate_bbox, validate_zoom])
    def get(self):
        return get_heatmap_response(ROUTE_TYPE, self.request)


@resource(path='/routes/map/tracks', cors_policy=cors_policy)
class RoutesTracksRest(ACLDefault):
    @view(validators=[validate_bbox, validate_preferred_lang_param])
    def get(self):
        return get_tracks_response(ROUTE_TYPE, Route, RouteLocale, self.request)
