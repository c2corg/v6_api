"""The orphan images: images linked to no document, listed for the moderators."""

# An image becomes an orphan when the documents it was linked to are deleted
# (the personal images of their author are deleted with them, see
# views.document_delete.personal_images_deleted_with), or when its links are
# removed. The images have no association data in the search index: the list
# reads the database.

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.sql.functions import func

from c2corg_api.models import DBSession
from c2corg_api.models.association import Association, AssociationLog
from c2corg_api.models.common.attributes import default_langs
from c2corg_api.models.document import Document, DocumentLocale
from c2corg_api.models.document_history import DocumentVersion, HistoryMetaData
from c2corg_api.models.image import Image
from c2corg_api.views.document_trash import _user, _users

LIMIT_DEFAULT = 30
LIMIT_MAX = 100


def _is_orphan():
    # two NOT EXISTS, not one with an OR: PostgreSQL runs them as hash anti
    # joins (0.2 s for 650k images instead of 1.6 s)
    return and_(
        Document.redirects_to.is_(None),
        ~exists().where(Association.parent_document_id == Image.document_id),
        ~exists().where(Association.child_document_id == Image.document_id),
    )


def list_orphan_images(offset, limit, image_type=None):
    """Return the images linked to no document, the last created first."""
    conditions = [_is_orphan()]
    if image_type is not None:
        conditions.append(Image.image_type == image_type)
    # Image includes the table of the documents
    base = select(Image.document_id, Image.filename, Image.image_type).where(
        *conditions
    )
    total = DBSession.execute(
        select(func.count()).select_from(base.subquery())
    ).scalar()
    # the ids follow the creation
    rows = DBSession.execute(
        base.order_by(Image.document_id.desc()).offset(offset).limit(limit)
    ).all()
    ids = [row.document_id for row in rows]
    created = _created(ids)
    unlinked = _last_unlinks(ids)
    users = _users(
        [user_id for _, user_id in created.values()]
        + [unlink['user_id'] for unlink in unlinked.values()]
    )
    titles = _titles(ids)
    return {
        'total': total,
        'images': [
            {
                'document_id': row.document_id,
                'filename': row.filename,
                'image_type': row.image_type,
                'title': titles.get(row.document_id),
                'created_at': _iso(created.get(row.document_id, (None, None))[0]),
                'author': _user(users, created.get(row.document_id, (None, None))[1]),
                'last_unlink': _unlink(unlinked.get(row.document_id), users),
            }
            for row in rows
        ],
    }


def _iso(value):
    return value.isoformat() if value is not None else None


def _created(ids):
    """Return when and by whom each image was created (its first version)."""
    if not ids:
        return {}
    rows = DBSession.execute(
        select(
            DocumentVersion.document_id,
            HistoryMetaData.written_at,
            HistoryMetaData.user_id,
        )
        .join(
            HistoryMetaData, HistoryMetaData.id == DocumentVersion.history_metadata_id
        )
        .where(DocumentVersion.document_id.in_(ids))
        .ext(distinct_on(DocumentVersion.document_id))
        .order_by(DocumentVersion.document_id, HistoryMetaData.id)
    )
    return {document_id: (at, user_id) for document_id, at, user_id in rows}


def _last_unlinks(ids):
    """Return the last link removed from each image, if any is known."""
    # the log of the links of a deleted document is deleted with it: the
    # images of deleted documents have none
    if not ids:
        return {}
    rows = DBSession.execute(
        select(AssociationLog)
        .where(
            or_(
                AssociationLog.child_document_id.in_(ids),
                AssociationLog.parent_document_id.in_(ids),
            ),
            AssociationLog.is_creation.is_(False),
        )
        .order_by(AssociationLog.written_at.desc())
    ).scalars()
    result = {}
    for log in rows:
        if log.child_document_id in ids:
            image_id = log.child_document_id
            other_id, other_type = log.parent_document_id, log.parent_document_type
        else:
            image_id = log.parent_document_id
            other_id, other_type = log.child_document_id, log.child_document_type
        result.setdefault(
            image_id,
            {
                'document_id': other_id,
                'document_type': other_type,
                'user_id': log.user_id,
                'written_at': log.written_at,
            },
        )
    return result


def _unlink(unlink, users):
    if unlink is None:
        return None
    return {
        'document_id': unlink['document_id'],
        'document_type': unlink['document_type'],
        'by': _user(users, unlink['user_id']),
        'at': _iso(unlink['written_at']),
    }


def _titles(ids):
    titles = {}
    for document_id, lang, title in DBSession.execute(
        select(
            DocumentLocale.document_id, DocumentLocale.lang, DocumentLocale.title
        ).where(DocumentLocale.document_id.in_(ids))
    ):
        titles.setdefault(document_id, {})[lang] = title
    return {
        document_id: next(
            (by_lang[lang] for lang in default_langs if lang in by_lang), None
        )
        for document_id, by_lang in titles.items()
    }


def read_orphan_images(request):
    """List the images linked to no document.

    Request:
        `GET` `/images/orphans?offset=0&limit=30&image_type=collaborative`
    """
    validated = request.validated
    return list_orphan_images(
        validated.get('offset') or 0,
        min(validated.get('limit') or LIMIT_DEFAULT, LIMIT_MAX),
        image_type=validated.get('image_type'),
    )
