from c2corg_api.models import DBSession
from c2corg_api.models.association import Association
from c2corg_api.models.image import IMAGE_TYPE, Image
from c2corg_api.models.outing import OUTING_TYPE
from c2corg_api.models.route import Route, ROUTE_TYPE
from c2corg_api.models.user import User
from c2corg_api.models.waypoint import Waypoint, WAYPOINT_TYPE
from c2corg_api.views.document_listings import get_documents_for_ids
from c2corg_api.views.document_schemas import waypoint_documents_config, \
    route_documents_config, user_profile_documents_config, \
    image_documents_config
from c2corg_api.views.validation import updatable_associations
from sqlalchemy.sql.expression import or_, and_

associations_to_include = {
    WAYPOINT_TYPE: {
        'waypoints', 'waypoint_children', 'routes', 'images'},
    ROUTE_TYPE:
        {'waypoints', 'routes', 'images'},
    OUTING_TYPE:
        {'waypoints', 'routes', 'images', 'users'},
    IMAGE_TYPE:
        {'waypoints', 'routes', 'images', 'users', 'outings'}
}


def get_associations(document, lang, editing_view):
    """Load and return associated documents.
    """
    types_to_include = associations_to_include.get(document.type, set())

    if editing_view:
        edit_types = updatable_associations.get(document.type, set())
        types_to_include = types_to_include.intersection(edit_types)

    associations = {}
    if 'waypoints' in types_to_include and \
            'waypoint_children' in types_to_include:
        associations['waypoints'] = get_linked_waypoint_parents(document, lang)
        associations['waypoint_children'] = \
            get_linked_waypoint_children(document, lang)
    elif 'waypoints' in types_to_include:
        associations['waypoints'] = get_linked_waypoints(document, lang)
    if 'routes' in types_to_include:
        if not editing_view and document.type == WAYPOINT_TYPE:
            # for waypoints the routes of child waypoints should also be
            # included (done in WaypointRest)
            pass
        else:
            associations['routes'] = get_linked_routes(document, lang)
    if 'users' in types_to_include:
        associations['users'] = get_linked_users(document, lang)
    if 'images' in types_to_include:
        associations['images'] = get_linked_images(document, lang)

    return associations


def get_linked_waypoint_parents(document, lang):
    waypoint_ids = _get_first_column(
        DBSession.query(Waypoint.document_id).
        filter(Waypoint.redirects_to.is_(None)).
        join(Association,
             Association.parent_document_id == Waypoint.document_id).
        filter(Association.child_document_id == document.document_id).
        group_by(Waypoint.document_id).
        all())

    return get_documents_for_ids(
        waypoint_ids, lang, waypoint_documents_config).get('documents')


def get_linked_waypoint_children(document, lang):
    waypoint_ids = _get_first_column(
        DBSession.query(Waypoint.document_id).
        filter(Waypoint.redirects_to.is_(None)).
        join(Association,
             Association.child_document_id == Waypoint.document_id).
        filter(Association.parent_document_id == document.document_id).
        group_by(Waypoint.document_id).
        all())

    return get_documents_for_ids(
        waypoint_ids, lang, waypoint_documents_config).get('documents')


def get_linked_waypoints(document, lang):
    waypoint_ids = _get_first_column(
        DBSession.query(Waypoint.document_id).
        filter(Waypoint.redirects_to.is_(None)).
        join(Association,
             or_(
                 Association.child_document_id == Waypoint.document_id,
                 Association.parent_document_id == Waypoint.document_id)).
        filter(
            or_(
                Association.parent_document_id == document.document_id,
                Association.child_document_id == document.document_id)).
        group_by(Waypoint.document_id).
        all())

    return get_documents_for_ids(
        waypoint_ids, lang, waypoint_documents_config).get('documents')


def get_linked_routes(document, lang):
    condition_as_child = and_(
        Association.child_document_id == Route.document_id,
        Association.parent_document_id == document.document_id)
    condition_as_parent = and_(
        Association.child_document_id == document.document_id,
        Association.parent_document_id == Route.document_id)

    if document.type == WAYPOINT_TYPE:
        condition = condition_as_child
    elif document.type in [OUTING_TYPE, IMAGE_TYPE]:
        condition = condition_as_parent
    else:
        condition = or_(condition_as_child, condition_as_parent)

    route_ids = _get_first_column(
        DBSession.query(Route.document_id).
        filter(Route.redirects_to.is_(None)).
        join(Association, condition).
        group_by(Route.document_id).
        all())

    return get_documents_for_ids(
        route_ids, lang, route_documents_config).get('documents')


def get_linked_users(document, lang):
    user_ids = _get_first_column(
        DBSession.query(User.id).
        join(Association, Association.parent_document_id == User.id).
        filter(Association.child_document_id == document.document_id).
        group_by(User.id).
        all())

    return get_documents_for_ids(
        user_ids, lang, user_profile_documents_config).get('documents')


def get_linked_images(document, lang):
    image_ids = _get_first_column(
        DBSession.query(Image.document_id).
        filter(Image.redirects_to.is_(None)).
        join(
            Association,
            and_(
                Association.child_document_id == Image.document_id,
                Association.parent_document_id == document.document_id)
            ).
        group_by(Image.document_id).
        all())

    return get_documents_for_ids(
        image_ids, lang, image_documents_config).get('documents')


def _get_first_column(rows):
    return [r for (r, ) in rows]
