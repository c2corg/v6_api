from sqlalchemy.sql.functions import func

from c2corg_api.models import DBSession
from c2corg_api.models.document import DocumentGeometry


def _envelope(bbox_3857):
    xmin, ymin, xmax, ymax = bbox_3857
    return func.ST_MakeEnvelope(xmin, ymin, xmax, ymax, 3857)


def get_track_ids(model, bbox_3857, limit, document_ids=None):
    """Return up to `limit + 1` ids of the `model` documents with a track in the bbox.

    The track (`geometry.geom_detail`) is the one that counts, not the point
    of the document: a long track is found even if its point is far from the
    bbox, and the documents without a track are not counted. The GIST index
    of the tracks answers it. `document_ids` restricts the documents.
    Callers should treat a result of length `limit + 1` as "too many results
    for this bbox".
    """
    if document_ids is not None and not document_ids:
        return []

    query = (
        DBSession.query(model.document_id)
        .join(DocumentGeometry, DocumentGeometry.document_id == model.document_id)
        .filter(model.redirects_to.is_(None))
        .filter(DocumentGeometry.geom_detail.isnot(None))
        .filter(DocumentGeometry.geom_detail.ST_Intersects(_envelope(bbox_3857)))
    )
    if document_ids is not None:
        query = query.filter(model.document_id.in_(document_ids))

    return [row.document_id for row in query.limit(limit + 1).all()]


def get_tracks(model, document_ids, tolerance, decimals, fields=()):
    """Return the `(document_id, geojson, *fields)` rows of the given documents.

    `geojson` is the track as GeoJSON text, made by the database: in 2D, its
    points simplified by `tolerance` (meters of EPSG:3857, about a pixel of
    the map) and written with `decimals` decimals. The track in the database
    is not changed. `fields` are the names of other columns of `model` to
    read. The most recent outings come first.
    """
    if not document_ids:
        return []

    # The points of the line that are not more than `tolerance` from it go. A
    # line that collapses (a short loop) is NULL: the line as it is, then, it
    # is short. The two arguments form is the one of every version of PostGIS.
    # No CRS member (options 0), whatever the version.
    flat = func.ST_Force2D(DocumentGeometry.geom_detail)
    geojson = func.ST_AsGeoJSON(
        func.coalesce(func.ST_Simplify(flat, tolerance), flat), decimals, 0
    ).label('geojson')

    # the most recent first: the outings by date, the other documents by id
    order = [model.document_id.desc()]
    if hasattr(model, 'date_end'):
        order.insert(0, model.date_end.desc())

    return (
        DBSession.query(
            model.document_id,
            geojson,
            *(getattr(model, field) for field in fields),
        )
        .join(DocumentGeometry, DocumentGeometry.document_id == model.document_id)
        .filter(model.document_id.in_(document_ids))
        .order_by(*order)
        .all()
    )


def get_titles(locale_model, document_ids):
    """Return the `(document_id, lang, title[, title_prefix])` rows of the locales.

    Only what a title needs: the descriptions and the other texts of the
    locales are not loaded. Callers can pick the best-matching locale per
    document (see `c2corg_api.views.get_best_locale`).
    """
    if not document_ids:
        return []

    columns = [locale_model.document_id, locale_model.lang, locale_model.title]
    if hasattr(locale_model, 'title_prefix'):
        columns.append(locale_model.title_prefix)

    return (
        DBSession.query(*columns)
        .filter(locale_model.document_id.in_(document_ids))
        .all()
    )
