"""The images shown in the texts of the documents ([img=ID] tags)."""

# guidebook.image_embeds is kept up to date when a locale is saved (see
# views.markdown.update_image_embeds). An embed is broken when its image does
# not exist (never did, or was deleted) or is another type of document. A
# merged image still shows (its target), its embeds are not broken.

from datetime import UTC, datetime

from sqlalchemy import Integer, cast, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB, aggregate_order_by, array_agg
from sqlalchemy.orm import aliased

from c2corg_api.models import DBSession
from c2corg_api.models.common.attributes import default_langs
from c2corg_api.models.deleted_document import RETENTION, DeletedDocument
from c2corg_api.models.document import Document, DocumentLocale
from c2corg_api.models.image import IMAGE_TYPE
from c2corg_api.models.image_embed import ImageEmbed

LIMIT_DEFAULT = 30
LIMIT_MAX = 100


def embedding_documents(image_ids, excluded_document_id=None):
    """Return the documents showing each image in their texts: {id: [doc]}."""
    # the image itself (its own description) is not another document
    image_ids = list(image_ids)
    if not image_ids:
        return {}
    conditions = [
        ImageEmbed.image_id.in_(image_ids),
        ImageEmbed.document_id != ImageEmbed.image_id,
        # a merged document is not shown
        Document.redirects_to.is_(None),
    ]
    if excluded_document_id is not None:
        conditions.append(ImageEmbed.document_id != excluded_document_id)
    rows = DBSession.execute(
        select(
            ImageEmbed.image_id,
            ImageEmbed.document_id,
            Document.type,
            array_agg(aggregate_order_by(ImageEmbed.lang, ImageEmbed.lang)),
        )
        .join(Document, Document.document_id == ImageEmbed.document_id)
        .where(*conditions)
        .group_by(ImageEmbed.image_id, ImageEmbed.document_id, Document.type)
        .order_by(ImageEmbed.image_id, ImageEmbed.document_id.desc())
    ).all()
    titles = document_titles({row[1] for row in rows})
    result = {}
    for image_id, document_id, document_type, langs in rows:
        result.setdefault(image_id, []).append(
            {
                'document_id': document_id,
                'document_type': document_type,
                'title': titles.get(document_id),
                'langs': langs,
            }
        )
    return result


def images_embedded_elsewhere(image_ids, document_id):
    """Return those of these images shown in the text of another document."""
    return set(embedding_documents(image_ids, excluded_document_id=document_id))


def document_titles(ids):
    """Return a title of each document, in the first of the default langs."""
    titles = {}
    if not ids:
        return titles
    for document_id, lang, title in DBSession.execute(
        select(
            DocumentLocale.document_id, DocumentLocale.lang, DocumentLocale.title
        ).where(DocumentLocale.document_id.in_(list(ids)))
    ):
        titles.setdefault(document_id, {})[lang] = title
    return {
        document_id: next(
            (by_lang[lang] for lang in default_langs if lang in by_lang), None
        )
        for document_id, by_lang in titles.items()
    }


def _restorable_images(cutoff):
    """Return the images that can be restored: (image id, last entry id)."""
    # the rows of an image are kept by the deletion of the image, of the
    # document it was deleted with (snapshot['deleted_images'], see
    # views.document_delete) or of the image it was merged into. Each entry
    # is read once: the snapshots are large.
    kept = (
        select(
            DeletedDocument.id.label('entry_id'),
            func.jsonb_array_elements(
                DeletedDocument.snapshot['tables'][Document.__table__.fullname],
                type_=JSONB,
            ).label('row'),
        )
        .where(
            DeletedDocument.restored_at.is_(None),
            DeletedDocument.deleted_at > cutoff,
            DeletedDocument.lang.is_(None),
        )
        .subquery()
    )
    return (
        select(
            cast(kept.c.row.op('->>')('document_id'), Integer).label('image_id'),
            func.max(kept.c.entry_id).label('entry_id'),
        )
        .where(kept.c.row.op('->>')('type') == IMAGE_TYPE)
        .group_by(kept.c.row.op('->>')('document_id'))
        .subquery()
    )


def list_broken_embeds(offset, limit):
    """Return the images shown in texts that do not show."""
    # the images that can still be restored first, the closest to their purge
    # first; then the last created documents first
    image = aliased(Document)
    cutoff = datetime.now(UTC) - RETENTION
    base = (
        select(
            ImageEmbed.document_id,
            ImageEmbed.image_id,
            Document.type.label('document_type'),
            image.type.label('image_document_type'),
            array_agg(aggregate_order_by(ImageEmbed.lang, ImageEmbed.lang)).label(
                'langs'
            ),
        )
        .join(Document, Document.document_id == ImageEmbed.document_id)
        .outerjoin(image, image.document_id == ImageEmbed.image_id)
        .where(
            Document.redirects_to.is_(None),
            or_(image.document_id.is_(None), image.type != IMAGE_TYPE),
        )
        .group_by(
            ImageEmbed.document_id, ImageEmbed.image_id, Document.type, image.type
        )
    )
    total = DBSession.execute(
        select(func.count()).select_from(base.subquery())
    ).scalar()
    broken = base.subquery()
    restorable = _restorable_images(cutoff)
    entry_id = restorable.c.entry_id
    rows = DBSession.execute(
        select(broken, entry_id)
        .outerjoin(restorable, restorable.c.image_id == broken.c.image_id)
        .order_by(
            entry_id.is_(None),
            entry_id,
            broken.c.document_id.desc(),
            broken.c.image_id,
        )
        .offset(offset)
        .limit(limit)
    ).all()
    entries = _entries({row.entry_id for row in rows} - {None})
    titles = document_titles({row.document_id for row in rows})
    return {
        'total': total,
        'embeds': [
            {
                'document_id': row.document_id,
                'document_type': row.document_type,
                'title': titles.get(row.document_id),
                'langs': row.langs,
                'image_id': row.image_id,
                'reason': _reason(row),
                # the document of this id when it is not an image
                'image_document_type': row.image_document_type,
                'deleted': entries.get(row.entry_id),
            }
            for row in rows
        ],
    }


def _reason(row):
    if row.image_document_type is not None:
        return 'not_image'
    return 'deleted' if row.entry_id is not None else 'missing'


def _entries(ids):
    """Return the deleted entries of these ids, to restore the images."""
    # import here: document_trash imports the views of the documents
    from c2corg_api.views.document_trash import _user, _users

    if not ids:
        return {}
    entries = (
        DBSession.execute(select(DeletedDocument).where(DeletedDocument.id.in_(ids)))
        .scalars()
        .all()
    )
    users = _users([entry.deleted_by for entry in entries])
    return {
        entry.id: {
            'entry_id': entry.id,
            # the document deleted with the image, or the image itself
            'document_id': entry.document_id,
            'document_type': entry.document_type,
            'deleted_at': entry.deleted_at.isoformat(),
            'expires_at': (entry.deleted_at + RETENTION).isoformat(),
            'by': _user(users, entry.deleted_by),
        }
        for entry in entries
    }


def read_broken_embeds(request):
    """List the images shown in the texts of documents that do not show."""
    # GET /images/broken-embeds?offset=0&limit=30
    validated = request.validated
    return list_broken_embeds(
        validated.get('offset') or 0,
        min(validated.get('limit') or LIMIT_DEFAULT, LIMIT_MAX),
    )
