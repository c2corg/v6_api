import functools
import json
import logging
import math

from shapely.errors import ShapelyError
from shapely.geometry import Point, shape

from c2corg_api.models import DBSession
from c2corg_api.models.common.fields_coverage import fields_coverage
from c2corg_api.models.coverage import (
    COVERAGE_TYPE,
    Coverage,
)
from c2corg_api.models.utils import wkb_to_shape
from c2corg_api.schemas.base import body_validator
from c2corg_api.schemas.coverage import (
    CoverageCreateSchema,
    CoverageUpdateSchema,
    coverage_schema,
)
from c2corg_api.views import restricted_json_view
from c2corg_api.views.document import (
    DocumentRest,
    make_validator_create,
    make_validator_update,
)
from c2corg_api.views.document_schemas import coverage_documents_config
from c2corg_api.views.resource import resource, view
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


@resource(collection_path='/coverages', path='/coverages/{id}')
class CoverageRest(DocumentRest):
    def __init__(self, request, context=None):
        self.request = request

    @view(validators=[validate_pagination, validate_preferred_lang_param])
    def collection_get(self):
        return self._collection_get(COVERAGE_TYPE, coverage_documents_config)

    @view(validators=[validate_id, validate_lang_param, validate_cook_param])
    def get(self):
        return self._get(
            coverage_documents_config, coverage_schema, include_areas=False
        )

    @restricted_json_view(
        validators=[
            body_validator(CoverageCreateSchema),
            validate_coverage_create,
            validate_associations_create,
        ],
    )
    def collection_post(self):
        return self._collection_post(coverage_schema, allow_anonymous=False)

    @restricted_json_view(
        validators=[
            body_validator(CoverageUpdateSchema),
            validate_id,
            validate_coverage_update,
            validate_associations_update,
        ],
    )
    def put(self):
        return self._put(Coverage, coverage_schema)


def validate_lon_lat(request, **kwargs):
    """Check that the required lon and lat are finite numbers."""
    for key in ('lon', 'lat'):
        try:
            value = float(request.GET[key])
            if not math.isfinite(value):
                raise ValueError
            request.validated[key] = value
        except KeyError, ValueError:
            request.errors.add('querystring', key, 'invalid ' + key)


@resource(path='/getcoverage')
class WaypointCoverageRest(DocumentRest):
    def __init__(self, request, context=None):
        self.request = request

    @view(validators=[validate_lon_lat])
    def get(self):
        """Return the coverage from a longitude and a latitude."""
        lon = self.request.validated['lon']
        lat = self.request.validated['lat']

        return get_coverage(lon, lat)


def validate_geom_detail(request, **kwargs):
    """Check that geom_detail is a GeoJSON geometry, given as a string."""
    # an invalid JSON body raises here: the catch-all error view answers it
    body = request.json_body
    try:
        request.validated['polygon'] = shape(json.loads(body['geom_detail']))
    except KeyError, TypeError, ValueError, AttributeError, ShapelyError:
        request.errors.add('body', 'geom_detail', 'invalid geom_detail')


@resource(path='/getpolygoncoverage')
class PolygonCoverage(DocumentRest):
    def __init__(self, request, context=None):
        self.request = request

    @view(validators=[validate_geom_detail])
    def post(self):
        """Return the coverages for a geom_detail polygon.

        Returns the coverages from a geom_detail type polygon
        (geom_detail has to be EPSG 4326 since isochrone is 4326).
        """
        return get_coverages(self.request.validated['polygon'])


def get_coverage(lon, lat):
    """Get the coverage that contains a point(lon, lat)."""
    pt = Point(lon, lat)

    coverage_found = None

    coverages = DBSession.query(Coverage).all()

    for coverage in coverages:
        geom = coverage.geometry.geom_detail

        # convert WKB → Shapely polygon
        poly = wkb_to_shape(geom)

        if poly.contains(pt):
            coverage_found = coverage
            break

    if coverage_found:
        return coverage_found.coverage_type
    else:
        return None


def get_coverages(polygon):
    """Get all the coverages that intersects a polygon."""
    coverage_found = []

    coverages = DBSession.query(Coverage).all()

    for coverage in coverages:
        geom = coverage.geometry.geom_detail

        # convert WKB → Shapely polygon
        poly = wkb_to_shape(geom)

        if poly.contains(polygon) or poly.intersects(polygon):
            coverage_found.append(coverage.coverage_type)

    return coverage_found
