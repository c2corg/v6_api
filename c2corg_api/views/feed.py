from collections import defaultdict

from c2corg_api.models import DBSession
from c2corg_api.models.feed import DocumentChange
from c2corg_api.models.image import IMAGE_TYPE
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.views.document_listings import get_documents_for_ids
from c2corg_api.views.document_schemas import document_configs
from c2corg_api.views.validation import validate_preferred_lang_param, \
    validate_token_pagination
from cornice.resource import resource, view
from c2corg_api.views import cors_policy
from sqlalchemy.sql.expression import or_, and_

DEFAULT_PAGE_LIMIT = 10
MAX_PAGE_LIMIT = 50


@resource(path='/feed', cors_policy=cors_policy)
class FeedRest(object):

    def __init__(self, request):
        self.request = request

    @view(validators=[
        validate_preferred_lang_param, validate_token_pagination])
    def get(self):
        """Get the public feed.

        Request:
            `GET` `/search[?pl=...][&limit=...][&token=...]`

        Parameters:

            `pl=...` (optional)
            When set only the given locale will be included (if available).
            Otherwise all locales will be returned.

            `limit=...` (optional)
            How many entries should be returned (default: 10).
            The maximum is 50.

            `token=...` (optional)
            The pagination token. When requesting a feed, the response includes
            a `pagination_token`. This token is to be used to request the next
            page.

            For more information about "continuation token pagination", see:
            http://www.servicedenuages.fr/pagination-continuation-token (fr)

        """
        lang = self.request.validated.get('lang')
        token_id = self.request.validated.get('token_id')
        token_time = self.request.validated.get('token_time')
        limit = self.request.validated.get('limit')
        limit = min(
            DEFAULT_PAGE_LIMIT if limit is None else limit,
            MAX_PAGE_LIMIT)

        changes = get_changes_of_public_feed(token_id, token_time, limit)
        return load_feed(changes, lang)


def get_changes_of_public_feed(token_id, token_time, limit):
    query = DBSession. \
        query(DocumentChange). \
        order_by(DocumentChange.time.desc(), DocumentChange.change_id)

    if token_id is not None and token_time:
        query = query.filter(
            or_(
                DocumentChange.time < token_time,
                and_(
                    DocumentChange.time == token_time,
                    DocumentChange.change_id > token_id)))

    return query.limit(limit).all()


def load_feed(changes, lang):
    """ Load the documents referenced in the given changes and build the feed.
    """
    if not changes:
        return {'feed': []}

    documents_to_load = get_documents_to_load(changes)
    documents = load_documents(documents_to_load, lang)

    last_change = changes[-1]
    pagination_token = '{},{}'.format(
        last_change.change_id, last_change.time.isoformat())

    return {
        'feed': [
            {
                'id': c.change_id,
                'time': c.time.isoformat(),
                'user': documents[c.user_id],
                'participants': [
                    documents[user_id] for user_id in c.user_ids
                    if user_id != c.user_id
                ],
                'change_type': c.change_type,
                'document': documents[c.document_id],
                'image1': documents[c.image1_id] if c.image1_id else None,
                'image2': documents[c.image2_id] if c.image2_id else None,
                'image3': documents[c.image3_id] if c.image3_id else None,
                'more_images': c.more_images
            } for c in changes
        ],
        'pagination_token': pagination_token
    }


def get_documents_to_load(changes):
    """ Return a dict containing the document ids (grouped by document type)
    that are needed for the given changes.

    For example given the changes:
        DocumentChange(
            user_id=1, document_id=2, document_type='o', user_ids={1, 3})
        DocumentChange(
            user_id=4, document_id=5, document_type='r', user_ids={4})

    ... the function would return:

        {
            'o': {2},
            'r': {5},
            'u': {1, 3, 4}
        }
    """
    documents_to_load = defaultdict(set)

    for change in changes:
        documents_to_load[change.document_type].add(change.document_id)

        documents_to_load[USERPROFILE_TYPE].add(change.user_id)
        documents_to_load[USERPROFILE_TYPE].update(change.user_ids)

        if change.image1_id:
            documents_to_load[IMAGE_TYPE].add(change.image1_id)
        if change.image2_id:
            documents_to_load[IMAGE_TYPE].add(change.image2_id)
        if change.image3_id:
            documents_to_load[IMAGE_TYPE].add(change.image3_id)

    return documents_to_load


def load_documents(documents_to_load, lang):
    documents = {}

    for document_type, document_ids in documents_to_load.items():
        document_config = document_configs[document_type]
        docs = get_documents_for_ids(
            document_ids, lang, document_config).get('documents')

        for doc in docs:
            documents[doc['document_id']] = doc

    return documents
