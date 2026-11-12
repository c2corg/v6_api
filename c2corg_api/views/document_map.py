import logging
import math
import os
import re

from c2corg_api.httpexceptions import HTTPServiceUnavailable
from c2corg_api.models.document_map_queries import get_titles, get_track_ids, get_tracks
from c2corg_api.models.outing import OUTING_TYPE, Outing, OutingLocale
from c2corg_api.models.route import ROUTE_TYPE, Route, RouteLocale
from c2corg_api.search.search_filters import build_query
from c2corg_api.views import get_best_locale

log = logging.getLogger(__name__)

# The environment variable that turns the map overlays off (the four endpoints
# answer 503 without touching the database nor the search index), when they
# load the servers too much. Read at each request: the value of the container
# is the one that counts.
TRACKS_OVERLAY_ENV = 'TRACKS_OVERLAY_ENABLED'
TRACKS_OVERLAY_OFF_VALUES = ('false', '0', 'no', 'off')

# Above this number of tracks in a bbox, the tracks endpoints report "too many
# results" (and the map shows their density) instead of returning a partial
# list. This is the default: the environment variable TRACKS_OVERLAY_MAX_TRACKS
# changes it without a new release, once the answers of a real server say how
# many a view can afford.
TRACKS_LIMIT_MAX = 100
TRACKS_LIMIT_ENV = 'TRACKS_OVERLAY_MAX_TRACKS'
# whatever the variable says: the answers would be too heavy
TRACKS_LIMIT_CEILING = 500

# maximum number of documents with a track in the bbox that are looked at
# (only their ids are read, and sent to the search index when filters are
# given)
# How long a browser or a proxy can keep an answer. The answers do not depend on
# who asks, and the UI asks for boxes on a grid: the same views are asked again
# and again. A new document shows within this time.
CACHE_SECONDS = 60
TRACKS_CANDIDATES_MAX = 5000

# The tracks are simplified by the database: the points of a line that are not
# more than `bbox width / TRACKS_SIMPLIFY_DIVISOR` meters from it are dropped,
# about a pixel of the map for a typical viewport.
TRACKS_SIMPLIFY_DIVISOR = 1500

# the most populated cells of the grid that are kept (the answer would be too
# big otherwise)
HEATMAP_BUCKETS_MAX = 5000

# The cells of the heatmap: about this many across the bbox, which the map
# blurs. The size of the cells comes from the bbox, never from the client: a
# fine grid cannot be asked over a large area.
HEATMAP_CELLS_ACROSS = 330

# the width of a geohash cell, by length of the geohash, at the equator (meters)
GEOHASH_CELL_WIDTH = {
    2: 1252300,
    3: 156500,
    4: 39100,
    5: 4890,
    6: 1220,
    7: 152.9,
    8: 38.2,
    9: 4.77,
}

# radius of the sphere used by EPSG:3857 (meters)
WEB_MERCATOR_RADIUS = 6378137

GEOHASH_BASE32 = '0123456789bcdefghjkmnpqrstuvwxyz'

# url parameters that are not search filters: `ids` is read here, `zoom` was the
# one of the first version of the heatmap, and the sort and the pagination of
# the listing mean nothing for a map (a `sort` on an unknown field is an error
# of the search index)
NON_FILTER_PARAMS = ('zoom', 'bbox', 'pl', 'ids', 'sort', 'offset', 'limit')


def _search_params(request):
    """Return the url parameters handled as search filters.

    They are the same ones as the documents listing, so that the map layers
    match a search made from the listing.
    """
    return {
        key: value
        for key in request.GET
        if key not in NON_FILTER_PARAMS and (value := request.GET.get(key))
    }


# `ids=` is a list of document ids, as long as that of the routes of an outing
IDS_MAX = 500


def validate_ids(request, **kwargs):
    """Check and parse the optional `ids=1,2` parameter.

    The list is stored in `request.validated['ids']`, or None if there is no
    such parameter. An empty list matches nothing.
    """
    value = request.GET.get('ids')
    if value is None:
        request.validated['ids'] = None
        return

    tokens = [token for token in value.split(',') if token]
    # ASCII digits, and the size of an id (not Unicode digits, nor numbers
    # that the database cannot take)
    if not all(re.fullmatch('[0-9]{1,9}', token) for token in tokens):
        request.errors.add('querystring', 'ids', 'invalid ids')
        return
    if len(tokens) > IDS_MAX:
        request.errors.add('querystring', 'ids', 'too many ids')
        return

    request.validated['ids'] = [int(token) for token in tokens]


def _document_ids(request):
    """Return the ids given by `ids=1,2`, or None if there is no such parameter."""
    return request.validated.get('ids')


def _heatmap_precision(bbox):
    """Return the geohash length (the cell size) for a heatmap of the bbox.

    Cells of a few pixels once on the screen, whatever the zoom: a coarser grid
    makes blobs, and a finer one is useless and costly.
    """
    xmin, ymin, xmax, ymax = bbox
    latitude = math.degrees(
        2 * math.atan(math.exp((ymin + ymax) / 2 / WEB_MERCATOR_RADIUS)) - math.pi / 2
    )
    # the cells shrink with the latitude, as the ground does in the projection
    stretch = math.cos(math.radians(latitude))
    wanted = (xmax - xmin) * stretch / HEATMAP_CELLS_ACROSS

    precision = min(GEOHASH_CELL_WIDTH)
    for candidate, width in GEOHASH_CELL_WIDTH.items():
        # the finest cells that are not much smaller than wanted (a finer grid
        # has too many cells: only the most populated ones are kept). The cells
        # go from one length to the next by a factor of 4 or 8, so the ones
        # chosen are between 0.8 and 6.4 times the wanted size: from 2 to 19
        # pixels for the 3 of the target
        if width * stretch >= wanted * 0.8:
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


def _bbox_param(bbox):
    return ','.join(str(value) for value in bbox)


def get_heatmap(doc_type, params, bbox, document_ids):
    """Return the density buckets (`{x, y, count}` in EPSG:3857).

    They are those of the documents matching the search filters in the bbox.
    """
    search = build_query(
        dict(params, bbox=_bbox_param(bbox)), {'limit': 0, 'offset': 0}, doc_type
    )
    if document_ids is not None:
        search = search.filter('ids', values=document_ids)
    search.aggs.bucket(
        'density',
        'geohash_grid',
        field='geom',
        precision=_heatmap_precision(bbox),
        size=HEATMAP_BUCKETS_MAX,
    )
    response = search.execute()

    buckets = []
    for bucket in response.aggregations.density.buckets:
        x, y = _lon_lat_to_3857(*_geohash_center(bucket.key))
        # meters are enough: the cells are tens of meters wide at least
        buckets.append({'x': round(x), 'y': round(y), 'count': bucket.doc_count})

    return {'buckets': buckets}


def _filtered_ids(doc_type, params, document_ids):
    """Return those of the ids that match the search filters."""
    # ids only, in any order: nothing is sorted nor read
    search = build_query(params, {'limit': len(document_ids), 'offset': 0}, doc_type)
    search = search.filter('ids', values=document_ids).sort()
    return [int(doc.meta.id) for doc in search.execute()]


def _matching_ids(doc_type, params, cap):
    """Return the ids matching the filters (anywhere), or None if over `cap`."""
    # Selective filters (`r`, `u`, `w`...) match few documents, wherever they
    # are: the database then has only these to look at.
    # The count comes first: a broad filter (`act=skitouring`) would otherwise
    # fetch `cap` hits only to drop them.
    search = build_query(params, {'limit': 0, 'offset': 0}, doc_type).sort()
    if search.execute().hits.total.value > cap:
        return None
    return [int(doc.meta.id) for doc in search.extra(size=cap).execute()]


def _titles_by_document_id(locale_model, document_ids, lang):
    locales_by_document = {}
    for locale in get_titles(locale_model, document_ids):
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


# what is read of a document next to its track, to tell the tracks apart: the
# activities, the dates of an outing and the ratings (the ones the listings
# show), for the documents that have them
TRACK_FIELDS = (
    'activities',
    'date_start',
    'date_end',
    'global_rating',
    'via_ferrata_rating',
    'rock_free_rating',
    'rock_required_rating',
    'aid_rating',
    'engagement_rating',
    'risk_rating',
    'equipment_rating',
    'exposition_rock_rating',
    'ice_rating',
    'mixed_rating',
    'ski_rating',
    'ski_exposition',
    'labande_global_rating',
    'labande_ski_rating',
    'snowshoe_rating',
    'hiking_rating',
    'mtb_up_rating',
    'mtb_down_rating',
    'hiking_mtb_exposition',
)


def _track_fields(row, fields):
    """Return the fields of a row that are set, as JSON values."""
    values = {}
    for field in fields:
        value = getattr(row, field)
        if value is None or value == []:
            continue
        values[field] = value.isoformat() if hasattr(value, 'isoformat') else value
    return values


def _simplification(bbox):
    """Return the `(tolerance, decimals)` of the tracks of a bbox.

    The tolerance is about a pixel of the map, in meters, and the coordinates
    have as many decimals as it needs.
    """
    tolerance = (bbox[2] - bbox[0]) / TRACKS_SIMPLIFY_DIVISOR
    if tolerance >= 1:
        decimals = 0
    elif tolerance >= 0.1:
        decimals = 1
    else:
        decimals = 2
    return tolerance, decimals


def _cacheable(request):
    request.response.headers['Cache-Control'] = f'public, max-age={CACHE_SECONDS}'


def get_tracks_response(doc_type, model, locale_model, request):
    _cacheable(request)
    params = _search_params(request)
    bbox = request.validated['bbox']
    lang = request.validated.get('lang')

    # Filters that match few documents (a route, a user...) come first, from
    # the search index: the database then only looks at these, whatever the
    # number of tracks in the view.
    document_ids = _document_ids(request)
    matching = None
    if params:
        matching = _matching_ids(doc_type, params, TRACKS_CANDIDATES_MAX)
        if matching is not None:
            given = None if document_ids is None else set(document_ids)
            document_ids = (
                matching if given is None else [i for i in matching if i in given]
            )
    filtered = matching is not None

    # What has a track in the bbox comes from the database, the ids only. It is
    # counted on the box of the tracks (not the exact tracks, see
    # `get_track_ids`): a view can be reported as truncated with `tracks_limit()`
    # tracks or fewer really crossing it, and the heatmap shows it then. The
    # search index then filters them, unless it already did, or there are no
    # filters. Without that second step, the answer is known from the first
    # `tracks_limit() + 1` ids.
    needs_filter = bool(params) and not filtered
    cap = TRACKS_CANDIDATES_MAX if needs_filter else tracks_limit()
    document_ids = get_track_ids(model, bbox, cap, document_ids=document_ids)
    if len(document_ids) > cap:
        return {'documents': [], 'truncated': True}
    if needs_filter and document_ids:
        document_ids = _filtered_ids(doc_type, params, document_ids)
    if len(document_ids) > tracks_limit():
        return {'documents': [], 'truncated': True}

    fields = tuple(field for field in TRACK_FIELDS if hasattr(model, field))
    tolerance, decimals = _simplification(bbox)
    rows = get_tracks(model, document_ids, tolerance, decimals, fields, bbox)
    titles = _titles_by_document_id(
        locale_model, [row.document_id for row in rows], lang
    )

    return {
        'documents': [
            {
                'document_id': row.document_id,
                'type': doc_type,
                'title': titles.get(row.document_id),
                'geometry': {'geom_detail': row.geojson},
                **_track_fields(row, fields),
            }
            for row in rows
        ],
        'truncated': False,
    }


def get_heatmap_response(doc_type, request):
    _cacheable(request)
    return get_heatmap(
        doc_type,
        _search_params(request),
        request.validated['bbox'],
        _document_ids(request),
    )


# The heatmap routes (web/document_map.py) return a grid of density buckets for
# the given bbox, meant to feed a heatmap layer.
#
#   `GET` `/{outings,routes}/map/heatmap?bbox=...[&<filters>]`
#
#   `bbox=xmin,ymin,xmax,ymax` (required, EPSG:3857): the size of the cells
#   comes from it, a few pixels once on the screen.
#
#   Any filter accepted by the documents listing (`act`, `r`, `date`, ...)
#   restricts the heatmap accordingly, and so does `ids=1,2`.
#
#   Response: `{"buckets": [{"x":.., "y":.., "count":..}]}`
#   Coordinates are in EPSG:3857, matching the map's projection.
#
# The tracks routes return individual tracks for the given bbox, meant to
# feed a vector layer once the number of tracks in the viewport is bounded.
#
#   `GET` `/{outings,routes}/map/tracks?bbox=...[&pl=...][&<filters>]`
#
#   Response: `{"documents": [{"document_id":.., "type": "o"|"r",
#   "title":.., "geometry": {"geom_detail": "<geojson>"}}],
#   "truncated": false}`
#
#   The tracks are in 2D and simplified for the screen (the track in the
#   database is not changed: the page of the document gives it as it is).
#
#   If more than `tracks_limit()` tracks cross the bbox, an empty,
#   `"truncated": true` response is returned instead of a silently
#   incomplete list: the frontend can ask the heatmap of the same bbox.


def tracks_limit():
    """Return the number of tracks above which a bbox has "too many" of them.

    It is `TRACKS_LIMIT_MAX` unless `TRACKS_OVERLAY_MAX_TRACKS` is a positive
    integer, and never more than `TRACKS_LIMIT_CEILING`. Read at each request,
    as the variable that turns the overlays off.
    """
    try:
        value = int(os.environ.get(TRACKS_LIMIT_ENV, ''))
    except ValueError:
        return TRACKS_LIMIT_MAX
    if value < 1:
        return TRACKS_LIMIT_MAX
    return min(value, TRACKS_LIMIT_CEILING)


def tracks_overlay_enabled():
    """Tell whether the map overlays are on (they are unless turned off)."""
    value = os.environ.get(TRACKS_OVERLAY_ENV, '')
    return value.strip().lower() not in TRACKS_OVERLAY_OFF_VALUES


def validate_tracks_overlay_enabled(request, **kwargs):
    """Refuse the request with a 503 when the overlays are turned off."""
    # the first validator: nothing else is worth doing then
    if not tracks_overlay_enabled():
        raise HTTPServiceUnavailable('the map overlays are turned off')


def read_outings_heatmap(request):
    return get_heatmap_response(OUTING_TYPE, request)


def read_outings_tracks(request):
    return get_tracks_response(OUTING_TYPE, Outing, OutingLocale, request)


def read_routes_heatmap(request):
    return get_heatmap_response(ROUTE_TYPE, request)


def read_routes_tracks(request):
    return get_tracks_response(ROUTE_TYPE, Route, RouteLocale, request)
