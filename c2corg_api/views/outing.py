from datetime import datetime, timedelta, timezone
import functools

from c2corg_api.models.outing import schema_outing, Outing, \
    schema_create_outing, schema_update_outing, ArchiveOuting, \
    ArchiveOutingLocale, OUTING_TYPE
from c2corg_api.models.utils import get_mid_point
from c2corg_api.views import cors_policy, restricted_json_view, \
    set_default_geom_from_associations
from c2corg_api.views.document import DocumentRest, make_validator_create, \
    make_validator_update
from c2corg_api.views.document_info import DocumentInfoRest
from c2corg_api.views.document_schemas import outing_documents_config, \
    outing_schema_adaptor, adapt_get_outing_response, \
    outing_documents_collection_config
from c2corg_api.views.document_version import DocumentVersionRest
from c2corg_api.views.validation import validate_id, validate_pagination, \
    validate_lang, validate_version_id, validate_lang_param, \
    validate_preferred_lang_param, validate_associations, \
    has_permission_for_outing, validate_cook_param
from c2corg_api.models.common.attributes import activities
from c2corg_api.models.common.fields_outing import fields_outing
from cornice.resource import resource, view
from cornice.validators import colander_body_validator
from pyramid.httpexceptions import HTTPForbidden

validate_outing_create = make_validator_create(
    fields_outing, 'activities', activities)
validate_outing_update = make_validator_update(
    fields_outing, 'activities', activities)
validate_associations_create = functools.partial(
    validate_associations, OUTING_TYPE, True)
validate_associations_update = functools.partial(
    validate_associations, OUTING_TYPE, False)


def _validate_dates(request, date_start, date_end):
    utc_now = datetime.now(timezone.utc)
    utc_now_plus_12h = (utc_now + timedelta(hours=12)).date()

    if isinstance(date_start, str):
        try:
            date_start = datetime.strptime(date_start, '%Y-%m-%d').date()
        except ValueError:
            request.errors.add(
                'body', 'date_start',
                'invalid format, expecting YEAR-MONTH-DAY'
            )

    if date_start > utc_now_plus_12h:
        request.errors.add(
            'body', 'date_start', 'can not be sometime in the future'
        )
        return

    if isinstance(date_end, str):
        try:
            date_end = datetime.strptime(date_end, '%Y-%m-%d').date()
        except ValueError:
            request.errors.add(
                'body', 'date_end',
                'invalid format, expecting YEAR-MONTH-DAY'
            )

    if date_end > utc_now_plus_12h:
        request.errors.add(
            'body', 'date_end', 'can not be sometime in the future'
        )

    if not request.errors and date_end < date_start:
        request.errors.add(
            'body', 'date_end', 'can not be prior the starting date'
        )


def validate_dates_on_creation(request, **kwargs):
    if request.errors:
        return

    date_start = request.validated.get('date_start')
    date_end = request.validated.get('date_end')

    _validate_dates(request, date_start, date_end)


def validate_dates_on_update(request, **kwargs):
    if request.errors:
        return

    document = request.validated.get('document')

    if document is None:  # other validators may have not validated doc
        return

    date_start = document.get('date_start')
    date_end = document.get('date_end')

    _validate_dates(request, date_start, date_end)


def validate_required_associations(request, **kwargs):
    missing_user = False
    missing_route = False

    associations = request.validated.get('associations', None)
    if not associations:
        missing_user = True
        missing_route = True
    else:
        linked_routes = associations.get('routes', [])
        if not linked_routes:
            missing_route = True

        linked_users = associations.get('users', [])
        if not linked_users:
            missing_user = True

    if missing_user:
        request.errors.add(
            'body', 'associations.users', 'at least one user required')

    if missing_route:
        request.errors.add(
            'body', 'associations.routes', 'at least one route required')


@resource(collection_path='/outings', path='/outings/{id}',
          cors_policy=cors_policy)
class OutingRest(DocumentRest):

    @view(validators=[
        validate_pagination, validate_preferred_lang_param])
    def collection_get(self):
        return self._collection_get(
            OUTING_TYPE,
            outing_documents_collection_config,
        )

    @view(validators=[validate_id, validate_lang_param, validate_cook_param])
    def get(self):
        return self._get(
            outing_documents_config,
            schema_outing,
            adapt_schema=outing_schema_adaptor,
            adapt_response=adapt_get_outing_response
        )

    @restricted_json_view(
        schema=schema_create_outing,
        validators=[
            colander_body_validator,
            validate_outing_create,
            validate_associations_create,
            validate_required_associations,
            validate_dates_on_creation])
    def collection_post(self):
        set_default_geom = functools.partial(
            set_default_geometry,
            self.request.validated['associations']['routes']
        )
        return self._collection_post(
            schema_outing, before_add=set_default_geom)

    @restricted_json_view(
        schema=schema_update_outing,
        validators=[
            colander_body_validator,
            validate_id,
            validate_outing_update,
            validate_associations_update,
            validate_required_associations,
            validate_dates_on_update])
    def put(self):
        if not has_permission_for_outing(
                self.request, self.request.validated['id']):
            # moderators can change every outing, but a normal user can only
            # change an outing that they are associated to
            raise HTTPForbidden('No permission to change this outing')
        return self._put(
            Outing, schema_outing, before_update=update_default_geometry)


@resource(path='/outings/{id}/{lang}/info', cors_policy=cors_policy)
class OutingInfoRest(DocumentInfoRest):

    @view(validators=[validate_id, validate_lang])
    def get(self):
        return self._get_document_info(outing_documents_config)


def set_default_geometry(linked_routes, outing, user_id):
    """When creating a new outing, set the default geometry to the middle point
    of a given track, if not to the centroid of the convex hull
    of all associated routes.
    """
    if outing.geometry is not None and outing.geometry.geom is not None:
        # default geometry already set
        return

    if outing.geometry is not None and outing.geometry.geom_detail is not None:
        # track is given, obtain a default point from the track
        outing.geometry.geom = get_mid_point(outing.geometry.geom_detail)
        return

    set_default_geom_from_associations(outing, linked_routes)


def update_default_geometry(outing, outing_in):
    """When updating an outing, set the default geometry to the middle point
    of a new track if proovided
    """

    geometry_in = outing_in.geometry

    if geometry_in is not None and geometry_in.geom_detail is not None:
        # update the default geom with the new track
        geometry_in.geom = get_mid_point(geometry_in.geom_detail)


@resource(path='/outings/{id}/{lang}/{version_id}', cors_policy=cors_policy)
class OutingVersionRest(DocumentVersionRest):

    @view(validators=[validate_id, validate_lang, validate_version_id])
    def get(self):
        return self._get_version(
            ArchiveOuting, OUTING_TYPE, ArchiveOutingLocale, schema_outing,
            outing_schema_adaptor)
