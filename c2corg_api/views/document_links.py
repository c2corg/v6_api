"""The documents linked in the texts of the documents ([[type/id|label]], URLs)."""

# guidebook.document_links is kept up to date when a locale is saved (see
# views.markdown.update_text_references). A link is broken when its target
# does not exist (never did, or was deleted), or is not of the type the link
# says: the page of the link does not show it. A merged target redirects: its
# links are not broken. Only the links of the collaborative documents are
# listed: the others (outings, personal documents...) are their authors'.

from datetime import UTC, datetime

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.dialects.postgresql import aggregate_order_by, array_agg
from sqlalchemy.orm import aliased

from c2corg_api.models import DBSession
from c2corg_api.models.area import AREA_TYPE
from c2corg_api.models.article import ARTICLE_TYPE, Article
from c2corg_api.models.book import BOOK_TYPE
from c2corg_api.models.deleted_document import RETENTION
from c2corg_api.models.document import Document
from c2corg_api.models.document_link import LINK_TYPES, DocumentLink
from c2corg_api.models.image import IMAGE_TYPE, Image
from c2corg_api.models.route import ROUTE_TYPE
from c2corg_api.models.topo_map import MAP_TYPE
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.models.waypoint import WAYPOINT_TYPE
from c2corg_api.views.image_embeds import (
    LIMIT_DEFAULT,
    LIMIT_MAX,
    document_titles,
    entries,
    restorable_documents,
)

# the types of v5, which the site redirects (/summits/123 to /waypoints/123):
# right in a URL, not in a [[type/id|label]] (the page builds the link itself)
URL_TYPES = {
    **LINK_TYPES,
    'huts': WAYPOINT_TYPE,
    'parkings': WAYPOINT_TYPE,
    'products': WAYPOINT_TYPE,
    'sites': WAYPOINT_TYPE,
    'summits': WAYPOINT_TYPE,
    'users': USERPROFILE_TYPE,
}

COLLABORATIVE_TYPES = [AREA_TYPE, BOOK_TYPE, MAP_TYPE, ROUTE_TYPE, WAYPOINT_TYPE]


def _expected_type():
    """Return the type of document a link shows (SQL), None for an unknown type."""
    return case(
        (
            DocumentLink.is_url,
            case(URL_TYPES, value=DocumentLink.target_type, else_=None),
        ),
        else_=case(LINK_TYPES, value=DocumentLink.target_type, else_=None),
    )


def linking_documents(target_ids, target_type, excluded_document_id=None):
    """Return the documents linking to each target in their texts: {id: [doc]}."""
    # only the links that show it: of its type (a link to a route that is an
    # image is broken anyway); the target itself is not another document
    target_ids = list(target_ids)
    if not target_ids:
        return {}
    conditions = [
        DocumentLink.target_id.in_(target_ids),
        DocumentLink.document_id != DocumentLink.target_id,
        _expected_type() == target_type,
        # a merged document is not shown
        Document.redirects_to.is_(None),
    ]
    if excluded_document_id is not None:
        conditions.append(DocumentLink.document_id != excluded_document_id)
    rows = DBSession.execute(
        select(
            DocumentLink.target_id,
            DocumentLink.document_id,
            Document.type,
            array_agg(
                aggregate_order_by(DocumentLink.lang.distinct(), DocumentLink.lang)
            ),
        )
        .join(Document, Document.document_id == DocumentLink.document_id)
        .where(*conditions)
        .group_by(DocumentLink.target_id, DocumentLink.document_id, Document.type)
        .order_by(DocumentLink.target_id, DocumentLink.document_id.desc())
    ).all()
    titles = document_titles({row[1] for row in rows})
    result = {}
    for target_id, document_id, document_type, langs in rows:
        result.setdefault(target_id, []).append(
            {
                'document_id': document_id,
                'document_type': document_type,
                'title': titles.get(document_id),
                'langs': langs,
            }
        )
    return result


def collaborative(document):
    """Return the condition (SQL) that the document is collaborative."""
    articles = Article.__table__
    images = Image.__table__
    return or_(
        document.type.in_(COLLABORATIVE_TYPES),
        and_(
            document.type == ARTICLE_TYPE,
            select(articles.c.article_type)
            .where(articles.c.document_id == document.document_id)
            .scalar_subquery()
            == 'collab',
        ),
        and_(
            document.type == IMAGE_TYPE,
            select(images.c.image_type)
            .where(images.c.document_id == document.document_id)
            .scalar_subquery()
            == 'collaborative',
        ),
    )


def list_broken_links(offset, limit):
    """Return the links in the texts of collaborative documents that are broken."""
    # the targets that can still be restored first, the closest to their
    # purge first; then the last created documents first
    target = aliased(Document)
    expected = _expected_type()
    cutoff = datetime.now(UTC) - RETENTION
    base = (
        select(
            DocumentLink.document_id,
            DocumentLink.target_id,
            DocumentLink.target_type,
            DocumentLink.is_url,
            Document.type.label('document_type'),
            target.type.label('target_document_type'),
            expected.label('expected_type'),
            array_agg(
                aggregate_order_by(DocumentLink.lang.distinct(), DocumentLink.lang)
            ).label('langs'),
        )
        .join(Document, Document.document_id == DocumentLink.document_id)
        .outerjoin(target, target.document_id == DocumentLink.target_id)
        .where(
            Document.redirects_to.is_(None),
            collaborative(Document),
            or_(
                target.document_id.is_(None),
                expected.is_(None),
                target.type != expected,
            ),
        )
        .group_by(
            DocumentLink.document_id,
            DocumentLink.target_id,
            DocumentLink.target_type,
            DocumentLink.is_url,
            Document.type,
            target.type,
        )
    )
    total = DBSession.execute(
        select(func.count()).select_from(base.subquery())
    ).scalar()
    broken = base.subquery()
    restorable = restorable_documents(cutoff, document_type=None)
    entry_id = restorable.c.entry_id
    rows = DBSession.execute(
        select(broken, entry_id)
        .outerjoin(
            restorable,
            and_(
                restorable.c.document_id == broken.c.target_id,
                # a target that does not exist: a restore brings it back
                broken.c.target_document_type.is_(None),
            ),
        )
        .order_by(
            entry_id.is_(None),
            entry_id,
            broken.c.document_id.desc(),
            broken.c.target_id,
            broken.c.target_type,
        )
        .offset(offset)
        .limit(limit)
    ).all()
    deleted = entries({row.entry_id for row in rows} - {None})
    titles = document_titles(
        {row.document_id for row in rows}
        | {row.target_id for row in rows if row.target_document_type is not None}
    )
    return {
        'total': total,
        'links': [
            {
                'document_id': row.document_id,
                'document_type': row.document_type,
                'title': titles.get(row.document_id),
                'langs': row.langs,
                'target_id': row.target_id,
                # as written: "routes", "summits"...
                'target_type': row.target_type,
                'is_url': row.is_url,
                'reason': _reason(row),
                # the document of this id, when it exists
                'target_document_type': row.target_document_type,
                'target_document_title': (
                    titles.get(row.target_id)
                    if row.target_document_type is not None
                    else None
                ),
                'deleted': deleted.get(row.entry_id),
            }
            for row in rows
        ],
    }


def _reason(row):
    if row.target_document_type is None:
        return 'deleted' if row.entry_id is not None else 'missing'
    # the type written is not one of the site, or not the one of the target
    return 'unknown_type' if row.expected_type is None else 'wrong_type'


def read_broken_links(request):
    """List the links in the texts of collaborative documents that are broken."""
    # GET /documents/broken-links?offset=0&limit=30
    validated = request.validated
    return list_broken_links(
        validated.get('offset') or 0,
        min(validated.get('limit') or LIMIT_DEFAULT, LIMIT_MAX),
    )
