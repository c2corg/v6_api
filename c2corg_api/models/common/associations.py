from c2corg_api.models.common.document_types import ROUTE_TYPE, OUTING_TYPE, \
    WAYPOINT_TYPE, USERPROFILE_TYPE, IMAGE_TYPE, ARTICLE_TYPE, AREA_TYPE, \
    BOOK_TYPE, XREPORT_TYPE

valid_associations = {
    # associations with outings
    (ROUTE_TYPE, OUTING_TYPE),
    (USERPROFILE_TYPE, OUTING_TYPE),

    # associations with waypoints
    (WAYPOINT_TYPE, WAYPOINT_TYPE),

    # associations with routes
    (ROUTE_TYPE, ROUTE_TYPE),
    (WAYPOINT_TYPE, ROUTE_TYPE),

    # associations with images
    (IMAGE_TYPE, IMAGE_TYPE),
    (WAYPOINT_TYPE, IMAGE_TYPE),
    (OUTING_TYPE, IMAGE_TYPE),
    (ROUTE_TYPE, IMAGE_TYPE),
    (USERPROFILE_TYPE, IMAGE_TYPE),
    (AREA_TYPE, IMAGE_TYPE),

    # associations with articles
    (ARTICLE_TYPE, ARTICLE_TYPE),
    (ARTICLE_TYPE, IMAGE_TYPE),
    (WAYPOINT_TYPE, ARTICLE_TYPE),
    (OUTING_TYPE, ARTICLE_TYPE),
    (ROUTE_TYPE, ARTICLE_TYPE),
    (USERPROFILE_TYPE, ARTICLE_TYPE),

    # associations with books
    (BOOK_TYPE, ROUTE_TYPE),
    (BOOK_TYPE, ARTICLE_TYPE),
    (BOOK_TYPE, IMAGE_TYPE),
    (BOOK_TYPE, WAYPOINT_TYPE),

    # associations with accidents
    (WAYPOINT_TYPE, XREPORT_TYPE),
    (USERPROFILE_TYPE, XREPORT_TYPE),
    (ROUTE_TYPE, XREPORT_TYPE),
    (OUTING_TYPE, XREPORT_TYPE),
    (XREPORT_TYPE, ARTICLE_TYPE),
    (XREPORT_TYPE, IMAGE_TYPE),
}
