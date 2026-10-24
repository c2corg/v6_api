import functools
import json
import logging
import time

from cornice.resource import resource, view
from cornice.validators import colander_body_validator
from shapely.geometry import Point, shape

from c2corg_api.models import DBSession
from c2corg_api.models.common.fields_coverage import fields_coverage
from c2corg_api.models.coverage import (
    COVERAGE_TYPE,
    Coverage,
    schema_coverage,
    schema_create_coverage,
    schema_update_coverage,
)
from c2corg_api.models.utils import wkb_to_shape
from c2corg_api.views import cors_policy, restricted_json_view
from c2corg_api.views.document import (
    DocumentRest,
    make_validator_create,
    make_validator_update,
)
from c2corg_api.views.document_schemas import coverage_documents_config
from c2corg_api.views.validation import (
    validate_associations,
    validate_cook_param,
    validate_id,
    validate_lang_param,
    validate_pagination,
    validate_preferred_lang_param,
)

log = logging.getLogger(__name__)

validate_coverage_create = make_validator_create(fields_coverage.get('required'))
validate_coverage_update = make_validator_update(fields_coverage.get('required'))
validate_associations_create = functools.partial(
    validate_associations, COVERAGE_TYPE, True
)
validate_associations_update = functools.partial(
    validate_associations, COVERAGE_TYPE, False
)


@resource(collection_path='/coverages', path='/coverages/{id}', cors_policy=cors_policy)
class CoverageRest(DocumentRest):
    def __init__(self, request, context=None):
        self.request = request

    @view(validators=[validate_pagination, validate_preferred_lang_param])
    def collection_get(self):
        return self._collection_get(COVERAGE_TYPE, coverage_documents_config)

    @view(validators=[validate_id, validate_lang_param, validate_cook_param])
    def get(self):
        return self._get(
            coverage_documents_config, schema_coverage, include_areas=False
        )

    @restricted_json_view(
        schema=schema_create_coverage,
        validators=[
            colander_body_validator,
            validate_coverage_create,
            validate_associations_create,
        ],
    )
    def collection_post(self):
        return self._collection_post(schema_coverage, allow_anonymous=False)

    @restricted_json_view(
        schema=schema_update_coverage,
        validators=[
            colander_body_validator,
            validate_id,
            validate_coverage_update,
            validate_associations_update,
        ],
    )
    def put(self):
        return self._put(Coverage, schema_coverage)


@resource(path='/getcoverage', cors_policy=cors_policy)
class WaypointCoverageRest(DocumentRest):
    def __init__(self, request, context=None):
        self.request = request

    @view(validators=[])
    def get(self):
        """Return the coverage from a longitude and a latitude."""
        lon = float(self.request.GET['lon'])
        lat = float(self.request.GET['lat'])

        return get_coverage(lon, lat)


@resource(path='/getpolygoncoverage', cors_policy=cors_policy)
class PolygonCoverage(DocumentRest):
    def __init__(self, request, context=None):
        self.request = request

    @view(validators=[])
    def post(self):
        """Return the coverages for a geom_detail polygon.

        Returns the coverages from a geom_detail type polygon
        (geom_detail has to be EPSG 4326 since isochrone is 4326).
        """
        geom_detail = json.loads(json.loads(self.request.body)['geom_detail'])
        polygon = shape(geom_detail)
        return get_coverages(polygon)


# The coverages (and their polygons) almost never change, but parsing all
# their geometries is costly and done for every Navitia call: keep the parsed
# polygons in memory for a few minutes. Each worker process has its own copy,
# so a modified coverage is picked up by every worker after this delay.
COVERAGES_CACHE_TTL = 300

_coverages_cache = {'loaded_at': None, 'coverages': []}


def _get_coverage_polygons():
    """Return the list of (coverage_type, shapely polygon)."""
    loaded_at = _coverages_cache['loaded_at']
    if loaded_at is None or time.monotonic() - loaded_at > COVERAGES_CACHE_TTL:
        _coverages_cache['coverages'] = [
            (coverage.coverage_type, wkb_to_shape(coverage.geometry.geom_detail))
            for coverage in DBSession.query(Coverage).all()
        ]
        _coverages_cache['loaded_at'] = time.monotonic()

    return _coverages_cache['coverages']


def clear_coverages_cache():
    """Forget the cached coverage polygons (they are loaded again on demand)."""
    _coverages_cache['loaded_at'] = None
    _coverages_cache['coverages'] = []


def get_coverage(lon, lat):
    """Get the coverage that contains a point(lon, lat)."""
    pt = Point(lon, lat)

    for coverage_type, poly in _get_coverage_polygons():
        if poly.contains(pt):
            return coverage_type

    return None


def get_coverages(polygon):
    """Get all the coverages that intersects a polygon."""
    return [
        coverage_type
        for coverage_type, poly in _get_coverage_polygons()
        if poly.contains(polygon) or poly.intersects(polygon)
    ]
