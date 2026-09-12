import logging

from cornice.resource import resource, view

from c2corg_api.caching import cache_outing_map, get_or_create
from c2corg_api.ext.colander_ext import geojson_from_wkbelement
from c2corg_api.models.outing import OUTING_TYPE
from c2corg_api.models.outing_map_queries import (
    get_locales_for_documents, get_outings_heatmap, get_outings_tracks)
from c2corg_api.security.acl import ACLDefault
from c2corg_api.views import cors_policy, get_best_locale
from c2corg_api.views.validation import validate_activities, \
    validate_bbox, validate_preferred_lang_param, validate_zoom

log = logging.getLogger(__name__)

# above this number of individual tracks in a bbox, the tracks endpoint
# reports "too many results" instead of returning a partial list
TRACKS_LIMIT_MAX = 100

# grid cell size (in meters, EPSG:3857) used to bucket outings for the
# heatmap, indexed by zoom level. The frontend is only expected to call
# this endpoint below the zoom level where it switches to the tracks
# endpoint, so no entries are needed for very high zoom levels.
HEATMAP_CELL_SIZE_BY_ZOOM = {
    0: 40000,
    1: 40000,
    2: 40000,
    3: 30000,
    4: 20000,
    5: 15000,
    6: 10000,
    7: 8000,
    8: 5000,
    9: 3000,
    10: 2000,
    11: 1200,
    12: 700,
}


def _cell_size_for_zoom(zoom):
    known_zooms = HEATMAP_CELL_SIZE_BY_ZOOM.keys()
    clamped_zoom = min(max(zoom, min(known_zooms)), max(known_zooms))
    return HEATMAP_CELL_SIZE_BY_ZOOM[clamped_zoom]


def _rounded_bbox_key(bbox, grid=500):
    return ','.join(str(int(round(value / grid) * grid)) for value in bbox)


def _activities_key(activities):
    return ','.join(sorted(activities)) if activities else ''


def _titles_by_document_id(document_ids, lang):
    locales = get_locales_for_documents(document_ids)

    locales_by_document = {}
    for locale in locales:
        locales_by_document.setdefault(locale.document_id, {})[
            locale.lang] = locale

    titles = {}
    for document_id, available_locales in locales_by_document.items():
        best_locale = get_best_locale(available_locales, lang)
        if best_locale:
            titles[document_id] = best_locale.title
    return titles


@resource(path='/outings/map/heatmap', cors_policy=cors_policy)
class OutingsHeatmapRest(ACLDefault):

    @view(validators=[validate_bbox, validate_zoom, validate_activities])
    def get(self):
        """Returns a grid of outing-density buckets for the given bbox,
        meant to feed a heatmap layer at low/medium map zoom levels.

        Request:
            `GET` `/outings/map/heatmap?bbox=...&zoom=...[&act=...]`

        Parameters:
            `bbox=xmin,ymin,xmax,ymax` (required, EPSG:3857)

            `zoom=...` (required)
            The current map zoom level. Used server-side to pick a grid
            cell size, so that a client cannot request an arbitrarily
            fine-grained aggregation over a large area.

            `act=...` (optional, comma-separated activity codes)
            Restricts the heatmap to the given activities.

        Response:
            `{"cell_size": 1200, "buckets": [{"x":.., "y":.., "count":..}]}`
            Coordinates are in EPSG:3857, matching the map's projection.
        """
        bbox = self.request.validated['bbox']
        zoom = self.request.validated['zoom']
        activities = self.request.validated.get('activities')
        cell_size = _cell_size_for_zoom(zoom)

        cache_key = 'heatmap:{}:{}:{}'.format(
            _rounded_bbox_key(bbox), _activities_key(activities), cell_size)

        def create():
            rows = get_outings_heatmap(bbox, activities, cell_size)
            return {
                'cell_size': cell_size,
                'buckets': [
                    {'x': row.x, 'y': row.y, 'count': row.count}
                    for row in rows
                ]
            }

        return get_or_create(cache_outing_map, cache_key, create)


@resource(path='/outings/map/tracks', cors_policy=cors_policy)
class OutingsTracksRest(ACLDefault):

    @view(validators=[
        validate_bbox, validate_activities, validate_preferred_lang_param])
    def get(self):
        """Returns individual outing tracks for the given bbox, meant to
        feed a vector layer at high map zoom levels (once the number of
        outings in the viewport is bounded).

        Request:
            `GET` `/outings/map/tracks?bbox=...[&act=...][&pl=...]`

        Parameters:
            `bbox=xmin,ymin,xmax,ymax` (required, EPSG:3857)

            `act=...` (optional, comma-separated activity codes)

            `pl=...` (optional preferred language)

        Response (normal case):
            `{"outings": [{"document_id":.., "type": "o", "title":..,
            "geometry": {"geom_detail": "<geojson>"}}], "truncated": false}`

            If more than `TRACKS_LIMIT_MAX` outings intersect the bbox,
            an empty, `"truncated": true` response is returned instead of
            a silently-incomplete list, so that the frontend can prompt
            the user to zoom in further.
        """
        bbox = self.request.validated['bbox']
        activities = self.request.validated.get('activities')
        lang = self.request.validated.get('lang')

        cache_key = 'tracks:{}:{}:{}'.format(
            _rounded_bbox_key(bbox), _activities_key(activities), lang)

        def create():
            rows = get_outings_tracks(bbox, activities, TRACKS_LIMIT_MAX)
            if len(rows) > TRACKS_LIMIT_MAX:
                return {'outings': [], 'truncated': True}

            titles = _titles_by_document_id(
                [row.document_id for row in rows], lang)

            outings = [
                {
                    'document_id': row.document_id,
                    'type': OUTING_TYPE,
                    'title': titles.get(row.document_id),
                    'geometry': {
                        'geom_detail':
                            geojson_from_wkbelement(row.geom_detail)
                    }
                }
                for row in rows
            ]
            return {'outings': outings, 'truncated': False}

        return get_or_create(cache_outing_map, cache_key, create)
