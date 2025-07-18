from c2corg_api.models import DBSession
from c2corg_api.models.document import Document, ArchiveDocumentLocale
from c2corg_api.models.document_history import DocumentVersion, HistoryMetaData
from c2corg_api.models.outing import OUTING_TYPE
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.views import cors_policy
from c2corg_api.views.feed import get_params
from c2corg_api.views.validation import validate_simple_token_pagination, \
  validate_user_id_not_required

from sqlalchemy.sql.expression import desc

from cornice.resource import resource, view
from sqlalchemy.orm import joinedload, load_only


@resource(path='/documents/changes', cors_policy=cors_policy)
class ChangesDocumentRest(object):
    """ Unique class for returning history of changes in documents.
    """

    def __init__(self, request, **kwargs):
        self.request = request

    @view(validators=[validate_simple_token_pagination,
                      validate_user_id_not_required])
    def get(self):
        """Get the public document changes feed.

        Request:
            `GET` `/document/changes[&limit=...][&token=...][&u=]`

        Parameters:

            `limit=...` (optional)
            How many entries should be returned (default: 30).
            The maximum is 50.

            `token=...` (optional)
            The pagination token. When requesting a feed, the response includes
            a `pagination_token`. This token is to be used to request the next
            page.

            `u=...` (optional)
            Changes made by one user.

            For more information about "continuation token pagination", see:
            http://www.servicedenuages.fr/pagination-continuation-token (fr)
        """
        user_id = self.request.validated.get('u')
        lang, token_id, _, limit = get_params(self.request, 30)

        changes = get_changes_of_feed(token_id, limit, user_id)
        doc_ids = [change.history_metadata_id for change in changes]

        return load_feed(doc_ids, limit, user_id)


def get_changes_of_feed(token_id, limit, user_id=None):
    query = DBSession.query(DocumentVersion.history_metadata_id) \
        .join(HistoryMetaData) \
        .join(Document) \
        .filter(Document.type.notin_([OUTING_TYPE, USERPROFILE_TYPE])) \
        .order_by(desc(DocumentVersion.history_metadata_id))

    # pagination filter
    if token_id is not None:
        query = query.filter(DocumentVersion.history_metadata_id < token_id)

    if user_id is not None:
        query = query.filter(HistoryMetaData.user_id == user_id)

    return query.limit(limit).all()


def load_feed(doc_ids, limit, user_id=None):
    if not doc_ids:
        doc_changes = []
    else:
        doc_changes = DBSession.query(DocumentVersion) \
            .options(load_only('lang'),
                     joinedload('history_metadata').load_only(
                        HistoryMetaData.id,
                        HistoryMetaData.user_id,
                        HistoryMetaData.comment,
                        HistoryMetaData.written_at).
                     joinedload('user').load_only(
                        User.id,
                        User.name,
                        User.username,
                        User.lang)) \
            .options(joinedload('document').load_only(
                    Document.version,
                    Document.document_id,
                    Document.type,
                    Document.quality)) \
            .options(joinedload('document_locales_archive').load_only(
                    ArchiveDocumentLocale.title)) \
            .order_by(desc(DocumentVersion.id)) \
            .filter(DocumentVersion.history_metadata_id.in_(doc_ids)) \
            .limit(limit) \
            .all()

    if not doc_changes:
        return {'feed': []}

    last_change = doc_changes[-1]
    pagination_token = '{}'.format(last_change.history_metadata_id)

    return {
        'pagination_token': pagination_token,
        'feed': [serialize_change(ch) for ch in doc_changes]
    }


def serialize_change(change):
    return {
        'written_at': change.history_metadata.written_at.isoformat(),
        'lang': change.lang,
        'document': {
            'version': change.document.version,
            'document_id': change.document.document_id,
            'title': change.document_locales_archive.title,
            'type': change.document.type,
            'quality': change.document.quality
        },
        'user': {
            'user_id': change.history_metadata.user_id,
            'name': change.history_metadata.user.name,
            'username': change.history_metadata.user.username,
            'lang': change.history_metadata.user.lang
        },
        'version_id': change.id,
        'comment': change.history_metadata.comment
    }
