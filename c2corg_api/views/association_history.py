from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from c2corg_api import caching
from c2corg_api.caching import (
    LISTING_TOTAL_EXPIRATION,
    cache_listing_total,
    get_or_create,
)
from c2corg_api.models import DBSession
from c2corg_api.models.association import AssociationLog
from c2corg_api.models.document import Document, DocumentLocale
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import USERPROFILE_TYPE

# max/default sizes of requests
LIMIT_MAX = 500
LIMIT_DEFAULT = 50


# Unique class for returning history of a document's associations.


def read_association_history(request):
    validated = request.validated
    document_id = validated.get('d', None)
    user_id = validated.get('u', None)
    offset = validated.get('offset', 0)
    limit = min(validated.get('limit', LIMIT_DEFAULT), LIMIT_MAX)

    user_join = joinedload(AssociationLog.user).load_only(
        User.id,
        User.name,
        User.forum_username,
        User.robot,
        User.moderator,
        User.blocked,
    )

    child_join = (
        joinedload(AssociationLog.child_document)
        .load_only(Document.document_id, Document.type)
        .joinedload(Document.locales)
        .load_only(DocumentLocale.title, DocumentLocale.lang)
    )

    parent_join = (
        joinedload(AssociationLog.parent_document)
        .load_only(Document.document_id, Document.type)
        .joinedload(Document.locales)
        .load_only(DocumentLocale.title, DocumentLocale.lang)
    )

    query = (
        DBSession.query(AssociationLog)
        .options(user_join)
        .options(parent_join)
        .options(child_join)
    )

    if document_id:
        query = query.filter(
            or_(
                AssociationLog.parent_document_id == document_id,
                AssociationLog.child_document_id == document_id,
            )
        )

    if user_id:
        query = query.filter(AssociationLog.user_id == user_id)

    if document_id or user_id:
        count = query.count()
    else:
        # counting all the association changes reads the whole table: cache
        # it for a few minutes, as the total of the document listings
        count = get_or_create(
            cache_listing_total,
            f'association_log-{caching.CACHE_VERSION}',
            query.count,
            expiration_time=LISTING_TOTAL_EXPIRATION,
        )

    query = query.order_by(AssociationLog.id.desc()).limit(limit).offset(offset).all()

    return {
        'count': count,
        'associations': [serialize_association_log(log) for log in query],
    }


def serialize_document(document):
    result = {
        'document_id': document.document_id,
        'type': document.type,
        'locales': [serialize_locale(locale) for locale in document.locales],
    }

    if document.type == USERPROFILE_TYPE:
        result['name'] = document.name

    return result


def serialize_locale(locale):
    return {'lang': locale.lang, 'title': locale.title}


def serialize_association_log(log):
    return {
        'written_at': log.written_at.isoformat(),
        'is_creation': log.is_creation,
        'user': {
            'user_id': log.user.id,
            'name': log.user.name,
            'forum_username': log.user.forum_username,
            'robot': log.user.robot,
            'moderator': log.user.moderator,
            'blocked': log.user.blocked,
        },
        'child_document': serialize_document(log.child_document),
        'parent_document': serialize_document(log.parent_document),
    }
