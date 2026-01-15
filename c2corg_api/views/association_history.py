from sqlalchemy import or_
from sqlalchemy.orm import joinedload
from cornice.resource import resource, view
from c2corg_api.views import cors_policy
from c2corg_api.views.validation import (
    validate_pagination,
    validate_user_id_not_required,
    validate_document_id_not_required)
from c2corg_api.models import DBSession
from c2corg_api.models.user import User
from c2corg_api.models.document import Document, DocumentLocale
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.models.association import AssociationLog

# max/default sizes of requests
LIMIT_MAX = 500
LIMIT_DEFAULT = 50


@resource(path='/associations-history', cors_policy=cors_policy)
class HistoryAssociationRest(object):
    """ Unique class for returning history of a document's associations.
    """
    def __init__(self, request, **kwargs):
        self.request = request

    @view(validators=[validate_document_id_not_required,
                      validate_pagination,
                      validate_user_id_not_required])
    def get(self):
        validated = self.request.validated
        document_id = validated.get('d', None)
        user_id = validated.get('u', None)
        offset = validated.get('offset', 0)
        limit = min(validated.get('limit', LIMIT_DEFAULT), LIMIT_MAX)

        user_join = joinedload(AssociationLog.user) \
            .load_only(
                User.id,
                User.name,
                User.forum_username,
                User.robot,
                User.moderator,
                User.blocked
            )

        child_join = joinedload(AssociationLog.child_document) \
            .load_only(Document.document_id, Document.type) \
            .joinedload(Document.locales) \
            .load_only(DocumentLocale.title, DocumentLocale.lang)

        parent_join = joinedload(AssociationLog.parent_document) \
            .load_only(Document.document_id, Document.type) \
            .joinedload(Document.locales) \
            .load_only(DocumentLocale.title, DocumentLocale.lang)

        query = DBSession.query(AssociationLog) \
            .options(user_join) \
            .options(parent_join) \
            .options(child_join)

        if document_id:
            query = query.filter(or_(
                AssociationLog.parent_document_id == document_id,
                AssociationLog.child_document_id == document_id)
            )

        if user_id:
            query = query.filter(AssociationLog.user_id == user_id)

        count = query.count()

        query = query.order_by(AssociationLog.id.desc()) \
            .limit(limit) \
            .offset(offset) \
            .all()

        return {
            'count': count,
            'associations': [serialize_association_log(log) for log in query]
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
            'blocked': log.user.blocked
        },
        'child_document': serialize_document(log.child_document),
        'parent_document': serialize_document(log.parent_document),
    }
