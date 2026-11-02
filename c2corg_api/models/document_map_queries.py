from sqlalchemy.sql.functions import func

from c2corg_api.models import DBSession
from c2corg_api.models.document import DocumentGeometry


def get_tracks(model, document_ids, bbox_3857, limit):
    """Return the tracks of the given documents that intersect a bbox.

    Returns up to `limit + 1` `(document_id, geom_detail)` rows for the
    documents of type `model` among `document_ids` whose track
    (`geometry.geom_detail`) intersects the given bbox. Callers should treat
    a result of length `limit + 1` as "too many results for this bbox"
    rather than displaying a silently-truncated set.
    """
    if not document_ids:
        return []

    xmin, ymin, xmax, ymax = bbox_3857
    envelope = func.ST_MakeEnvelope(xmin, ymin, xmax, ymax, 3857)

    return (
        DBSession.query(model.document_id, DocumentGeometry.geom_detail)
        .join(DocumentGeometry, DocumentGeometry.document_id == model.document_id)
        .filter(model.document_id.in_(document_ids))
        .filter(model.redirects_to.is_(None))
        .filter(DocumentGeometry.geom_detail.isnot(None))
        .filter(DocumentGeometry.geom_detail.ST_Intersects(envelope))
        .order_by(model.document_id)
        .limit(limit + 1)
        .all()
    )


def get_locales_for_documents(locale_model, document_ids):
    """Return all locales of the given documents.

    Returns all `locale_model` rows for the given document ids, so that
    callers can pick the best-matching locale per document (see
    `c2corg_api.views.get_best_locale`).
    """
    if not document_ids:
        return []

    return (
        DBSession.query(locale_model)
        .filter(locale_model.document_id.in_(document_ids))
        .all()
    )
