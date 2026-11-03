import functools
from datetime import UTC, datetime, timedelta

from c2corg_api.httpexceptions import HTTPForbidden
from c2corg_api.models.common.attributes import activities
from c2corg_api.models.common.fields_outing import fields_outing
from c2corg_api.models.outing import (
    OUTING_TYPE,
    ArchiveOuting,
    ArchiveOutingLocale,
    Outing,
)
from c2corg_api.models.utils import get_mid_point
from c2corg_api.schemas.base import body_validator
from c2corg_api.schemas.outing import (
    OutingCreateSchema,
    OutingUpdateSchema,
    outing_schema,
)
from c2corg_api.views import (
    restricted_json_view,
    set_default_geom_from_associations,
)
from c2corg_api.views.document import (
    collection_get,
    create_document,
    make_validator_create,
    make_validator_update,
    put_document,
    read_document,
)
from c2corg_api.views.document_info import document_info
from c2corg_api.views.document_schemas import (
    outing_documents_config,
    outing_schema_adaptor,
)
from c2corg_api.views.document_version import document_version
from c2corg_api.views.resource import view
from c2corg_api.views.validation import (
    has_permission_for_outing,
    validate_associations,
    validate_cook_param,
    validate_id,
    validate_lang,
    validate_lang_param,
    validate_pagination,
    validate_preferred_lang_param,
    validate_version_id,
)

validate_outing_create = make_validator_create(fields_outing, 'activities', activities)
validate_outing_update = make_validator_update(fields_outing, 'activities', activities)
validate_associations_create = functools.partial(
    validate_associations, OUTING_TYPE, True
)
validate_associations_update = functools.partial(
    validate_associations, OUTING_TYPE, False
)


def _validate_dates(request, date_start, date_end):
    utc_now = datetime.now(UTC)
    utc_now_plus_12h = (utc_now + timedelta(hours=12)).date()

    if isinstance(date_start, str):
        try:
            date_start = datetime.strptime(date_start, '%Y-%m-%d').date()  # noqa: DTZ007 (date only)
        except ValueError:
            request.errors.add(
                'body', 'date_start', 'invalid format, expecting YEAR-MONTH-DAY'
            )

    if date_start > utc_now_plus_12h:
        request.errors.add('body', 'date_start', 'can not be sometime in the future')
        return

    if isinstance(date_end, str):
        try:
            date_end = datetime.strptime(date_end, '%Y-%m-%d').date()  # noqa: DTZ007 (date only)
        except ValueError:
            request.errors.add(
                'body', 'date_end', 'invalid format, expecting YEAR-MONTH-DAY'
            )

    if date_end > utc_now_plus_12h:
        request.errors.add('body', 'date_end', 'can not be sometime in the future')

    if not request.errors and date_end < date_start:
        request.errors.add('body', 'date_end', 'can not be prior the starting date')


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
        request.errors.add('body', 'associations.users', 'at least one user required')

    if missing_route:
        request.errors.add('body', 'associations.routes', 'at least one route required')


@restricted_json_view(
    validators=[
        body_validator(OutingCreateSchema),
        validate_outing_create,
        validate_associations_create,
        validate_required_associations,
        validate_dates_on_creation,
    ],
)
def create_outing(request):
    set_default_geom = functools.partial(
        set_default_geometry, request.validated['associations']['routes']
    )
    return create_document(request, outing_schema, before_add=set_default_geom)


@restricted_json_view(
    validators=[
        body_validator(OutingUpdateSchema),
        validate_id,
        validate_outing_update,
        validate_associations_update,
        validate_required_associations,
        validate_dates_on_update,
    ],
)
def update_outing(request):
    if not has_permission_for_outing(request, request.validated['id']):
        # moderators can change every outing, but a normal user can only
        # change an outing that they are associated to
        raise HTTPForbidden('No permission to change this outing')
    return put_document(
        request, Outing, outing_schema, before_update=update_default_geometry
    )


@view(validators=[validate_pagination, validate_preferred_lang_param])
def list_outings(request):
    return collection_get(request, OUTING_TYPE, outing_documents_config)


@view(validators=[validate_id, validate_lang_param, validate_cook_param])
def get_outing(request):
    return read_document(
        request,
        outing_documents_config,
        outing_schema,
        adapt_schema=outing_schema_adaptor,
    )


@view(validators=[validate_id, validate_lang])
def get_outing_info(request):
    return document_info(request, outing_documents_config)


def set_default_geometry(linked_routes, outing, user_id):
    """Set the default geometry of a new outing.

    When creating a new outing, set the default geometry to the middle point
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
    """Update the default geometry of an outing.

    When updating an outing, set the default geometry to the middle point
    of a new track if provided, unless the default geometry was moved.
    """
    geometry = outing.geometry
    geometry_in = outing_in.geometry

    if geometry_in is None or geometry_in.geom_detail is None:
        return

    if (
        geometry is not None
        and geometry.geom is not None
        and geometry_in.geom is not None
    ):
        if not geometry._almost_equals(geometry.geom, geometry_in.geom):
            # the default geom was placed by the user, keep it
            return
        if geometry._almost_equals(geometry.geom_detail, geometry_in.geom_detail):
            # the track has not changed, keep the current default geom
            return

    # update the default geom with the new track
    geometry_in.geom = get_mid_point(geometry_in.geom_detail)


@view(validators=[validate_id, validate_lang, validate_version_id])
def get_outing_version(request):
    return document_version(
        request,
        ArchiveOuting,
        OUTING_TYPE,
        ArchiveOutingLocale,
        outing_schema,
        outing_schema_adaptor,
    )
