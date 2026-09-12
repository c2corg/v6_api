from sqlalchemy.sql.functions import func

from c2corg_api.models import DBSession
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.outing import Outing


def _bbox_envelope(bbox_3857):
    xmin, ymin, xmax, ymax = bbox_3857
    return func.ST_MakeEnvelope(xmin, ymin, xmax, ymax, 3857)


def _filter_by_activities(query, activities):
    if activities:
        query = query.filter(Outing.activities.overlap(activities))
    return query


def get_outings_heatmap(bbox_3857, activities, cell_size_m):
    """Returns density buckets `(x, y, count)` for outings whose
    representative point (`geometry.geom`) falls in the given bbox, with
    coordinates snapped to a grid of `cell_size_m` meters (EPSG:3857).

    Bucketing uses the outing's single representative point rather than
    its track (`geom_detail`), so that one outing always contributes to
    exactly one bucket (a "density of outings" heatmap, not a "density of
    kilometers of track" one).
    """
    envelope = _bbox_envelope(bbox_3857)
    grid_point = func.ST_SnapToGrid(DocumentGeometry.geom, cell_size_m)

    query = (
        DBSession.query(
            func.ST_X(grid_point).label('x'),
            func.ST_Y(grid_point).label('y'),
            func.count(Outing.document_id).label('count'))
        .join(
            DocumentGeometry,
            DocumentGeometry.document_id == Outing.document_id)
        .filter(Outing.redirects_to.is_(None))
        .filter(DocumentGeometry.geom.isnot(None))
        .filter(DocumentGeometry.geom.ST_Intersects(envelope)))
    query = _filter_by_activities(query, activities)

    return query.group_by(grid_point).all()


def get_outings_tracks(bbox_3857, activities, limit):
    """Returns up to `limit + 1` `(document_id, geom_detail)` rows for
    outings whose track (`geometry.geom_detail`) intersects the given
    bbox. Callers should treat a result of length `limit + 1` as "too many
    results for this bbox" rather than displaying a silently-truncated
    set.
    """
    envelope = _bbox_envelope(bbox_3857)

    query = (
        DBSession.query(Outing.document_id, DocumentGeometry.geom_detail)
        .join(
            DocumentGeometry,
            DocumentGeometry.document_id == Outing.document_id)
        .filter(Outing.redirects_to.is_(None))
        .filter(DocumentGeometry.geom_detail.isnot(None))
        .filter(DocumentGeometry.geom_detail.ST_Intersects(envelope)))
    query = _filter_by_activities(query, activities)

    return query.limit(limit + 1).all()


def get_locales_for_documents(document_ids):
    """Returns all `DocumentLocale` rows for the given document ids, so
    that callers can pick the best-matching locale per document (see
    `c2corg_api.views.get_best_locale`).
    """
    if not document_ids:
        return []

    return (
        DBSession.query(DocumentLocale)
        .filter(DocumentLocale.document_id.in_(document_ids))
        .all())
