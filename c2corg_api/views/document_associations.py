from c2corg_api.models import DBSession
from c2corg_api.models.area import AREA_TYPE, Area
from c2corg_api.models.article import ARTICLE_TYPE, Article
from c2corg_api.models.association import Association
from c2corg_api.models.book import BOOK_TYPE, Book
from c2corg_api.models.image import IMAGE_TYPE, Image
from c2corg_api.models.outing import OUTING_TYPE, Outing
from c2corg_api.models.report import Report, REPORT_TYPE
from c2corg_api.models.route import Route, ROUTE_TYPE
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.models.waypoint import Waypoint, WAYPOINT_TYPE
from c2corg_api.views.document_listings import get_documents_for_ids
from c2corg_api.views.document_schemas import waypoint_documents_config, \
    route_documents_config, user_profile_documents_config, \
    image_documents_config, article_documents_config, area_documents_config, \
    outing_documents_config, book_documents_config, report_documents_config
from c2corg_api.views.validation import updatable_associations
from sqlalchemy.sql.expression import or_, and_

associations_to_include = {
    WAYPOINT_TYPE: {
        'waypoints', 'waypoint_children', 'routes', 'images', 'articles',
        'books'},
    ROUTE_TYPE:
        {'waypoints', 'routes', 'images', 'articles', 'books', 'reports'},
    OUTING_TYPE:
        {'routes', 'images', 'users', 'articles', 'reports'},
    IMAGE_TYPE:
        {'waypoints', 'routes', 'images', 'users', 'outings', 'articles',
         'areas', 'books', 'reports'},
    ARTICLE_TYPE:
        {'waypoints', 'routes', 'images', 'users', 'outings', 'articles',
         'books', 'reports'},
    AREA_TYPE: {'images'},
    BOOK_TYPE: {'routes', 'articles', 'images', 'waypoints'},
    REPORT_TYPE: {'routes', 'outings', 'articles', 'images'},
    USERPROFILE_TYPE: {'images'}
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
    if 'articles' in types_to_include:
        associations['articles'] = get_linked_articles(document, lang)
    if 'areas' in types_to_include:
        associations['areas'] = get_linked_areas(document, lang)
    if 'outings' in types_to_include:
        # for waypoints and routes, only the latest x outings are included
        # elsewhere (because there are potentially many)
        associations['outings'] = get_linked_outings(document, lang)
    if 'books' in types_to_include:
        associations['books'] = get_linked_books(document, lang)
    if 'reports' in types_to_include:
        associations['reports'] = get_linked_reports(document, lang)

    return associations


def get_linked_waypoint_parents(document, lang):
    waypoint_ids = get_first_column(
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
    waypoint_ids = get_first_column(
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
    waypoint_ids = get_first_column(
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
    elif document.type in [OUTING_TYPE, IMAGE_TYPE, ARTICLE_TYPE, REPORT_TYPE]:
        condition = condition_as_parent
    else:
        condition = or_(condition_as_child, condition_as_parent)

    route_ids = get_first_column(
        DBSession.query(Route.document_id).
        filter(Route.redirects_to.is_(None)).
        join(Association, condition).
        group_by(Route.document_id).
        all())

    return get_documents_for_ids(
        route_ids, lang, route_documents_config).get('documents')


def get_linked_users(document, lang):
    user_ids = get_first_column(
        DBSession.query(User.id).
        join(Association, Association.parent_document_id == User.id).
        filter(Association.child_document_id == document.document_id).
        group_by(User.id).
        all())

    return get_documents_for_ids(
        user_ids, lang, user_profile_documents_config).get('documents')


def get_linked_images(document, lang):
    image_ids = get_first_column(
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


def get_linked_areas(document, lang):
    area_ids = get_first_column(
        DBSession.query(Area.document_id).
        filter(Area.redirects_to.is_(None)).
        join(
            Association,
            and_(
                Association.parent_document_id == Area.document_id,
                Association.child_document_id == document.document_id)
            ).
        group_by(Area.document_id).
        all())

    return get_documents_for_ids(
        area_ids, lang, area_documents_config).get('documents')


def get_linked_outings(document, lang):
    outing_ids = get_first_column(
        DBSession.query(Outing.document_id).
        filter(Outing.redirects_to.is_(None)).
        join(
            Association,
            and_(
                Association.parent_document_id == Outing.document_id,
                Association.child_document_id == document.document_id)
            ).
        group_by(Outing.document_id).
        all())

    return get_documents_for_ids(
        outing_ids, lang, outing_documents_config).get('documents')


def get_linked_articles(document, lang):
    condition_as_child = and_(
        Association.child_document_id == Article.document_id,
        Association.parent_document_id == document.document_id
    )
    condition_as_parent = and_(
        Association.child_document_id == document.document_id,
        Association.parent_document_id == Article.document_id
    )

    if document.type == IMAGE_TYPE:
        condition = condition_as_parent
    elif document.type in [WAYPOINT_TYPE,
                           OUTING_TYPE,
                           ROUTE_TYPE,
                           BOOK_TYPE,
                           REPORT_TYPE,
                           USERPROFILE_TYPE]:
        condition = condition_as_child

    elif document.type == ARTICLE_TYPE:
        condition = or_(condition_as_child, condition_as_parent)

    article_ids = get_first_column(
        DBSession.query(Article.document_id).
        filter(Article.redirects_to.is_(None)).
        join(
            Association, condition).
        group_by(Article.document_id).
        all())

    return get_documents_for_ids(
        article_ids, lang, article_documents_config).get('documents')


def get_linked_books(document, lang):
    book_ids = get_first_column(
        DBSession.query(Book.document_id).
        filter(Book.redirects_to.is_(None)).
        join(
            Association,
            and_(
                Association.child_document_id == document.document_id,
                Association.parent_document_id == Book.document_id)
            ).
        group_by(Book.document_id).
        all())

    return get_documents_for_ids(
        book_ids, lang, book_documents_config).get('documents')


def get_linked_reports(document, lang):
    condition_as_child = and_(
        Association.child_document_id == Report.document_id,
        Association.parent_document_id == document.document_id
    )
    condition_as_parent = and_(
        Association.child_document_id == document.document_id,
        Association.parent_document_id == Report.document_id
    )

    if document.type in [ARTICLE_TYPE, IMAGE_TYPE]:
        condition = condition_as_parent
    elif document.type in [ROUTE_TYPE, OUTING_TYPE]:
        condition = condition_as_child

    report_ids = get_first_column(
        DBSession.query(Report.document_id).
        filter(Report.redirects_to.is_(None)).
        join(
            Association, condition).
        group_by(Report.document_id).
        all())

    return get_documents_for_ids(
        report_ids, lang, report_documents_config).get('documents')


def get_first_column(rows):
    return [r for (r, ) in rows]
