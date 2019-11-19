from collections import defaultdict

from c2corg_api.models import DBSession
from c2corg_api.models.feed import DocumentChange, FollowedUser, FilterArea
from c2corg_api.models.image import IMAGE_TYPE
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.views.document_listings import get_documents_for_ids
from c2corg_api.views.document_schemas import document_configs
from c2corg_api.views.validation import validate_preferred_lang_param, \
    validate_token_pagination, validate_user_id
from cornice.resource import resource, view
from c2corg_api.views import cors_policy, restricted_view
from pyramid.httpexceptions import HTTPNotFound, HTTPForbidden
from sqlalchemy.orm import undefer, load_only
from sqlalchemy.sql.expression import or_, and_
from sqlalchemy.sql.functions import func
from urllib import parse as urllib_parse

DEFAULT_PAGE_LIMIT = 10
MAX_PAGE_LIMIT = 50


@resource(path='/feed', cors_policy=cors_policy)
class FeedRest(object):

    def __init__(self, request):
        self.request = request

    @view(validators=[
        validate_preferred_lang_param, validate_token_pagination])
    def get(self):
        """Get the public homepage feed.

        Request:
            `GET` `/feed[?pl=...][&limit=...][&token=...]`

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
        lang, token_id, token_time, limit = get_params(self.request)
        ignore_admin_changes_filter = get_ignore_admin_entries_filter(
            self.request)
        changes = get_changes_of_feed(
            token_id, token_time, limit, ignore_admin_changes_filter)
        return load_feed(changes, lang)


@resource(path='/personal-feed', cors_policy=cors_policy)
class PersonalFeedRest(object):

    def __init__(self, request):
        self.request = request

    @restricted_view(validators=[
        validate_preferred_lang_param, validate_token_pagination])
    def get(self):
        """Get the personal homepage feed for the authenticated user.

        Request:
            `GET` `/personal-feed[?pl=...][&limit=...][&token=...]`

        Parameters: See above for '/feed'.

        """
        user_id = self.request.authenticated_userid
        lang, token_id, token_time, limit = get_params(self.request)
        ignore_admin_changes_filter = get_ignore_admin_entries_filter(
            self.request)
        changes = get_changes_of_personal_feed(
            user_id, token_id, token_time, limit, ignore_admin_changes_filter)
        return load_feed(changes, lang)


@resource(path='/profile-feed', cors_policy=cors_policy)
class ProfileFeedRest(object):

    def __init__(self, request):
        self.request = request

    @view(validators=[
        validate_preferred_lang_param, validate_token_pagination,
        validate_user_id])
    def get(self):
        """Get the user profile feed for a user.

        Request:
            `GET` `/profile-feed?u={user_id}[&pl=...][&limit=...][&token=...]`

        Parameters:

            `u={user_id}` (required)
            The id of the user whose profile feed is requested.

            For the other parameters, see above for '/feed'.

        """
        lang, token_id, token_time, limit = get_params(self.request)

        # load the requested user
        requested_user_id = self.request.validated['u']
        requested_user = DBSession.query(User). \
            filter(User.id == requested_user_id). \
            filter(User.email_validated). \
            options(load_only(User.id, User.is_profile_public)). \
            first()

        if not requested_user:
            raise HTTPNotFound('user not found')
        elif requested_user.is_profile_public or \
                self.request.has_permission('authenticated'):
            # only return the feed if authenticated or if the user marked
            # the profile as public
            changes = get_changes_of_profile_feed(
                requested_user_id, token_id, token_time, limit)
            return load_feed(changes, lang)
        else:
            raise HTTPForbidden('no permission to see the feed')


def get_params_type_filter(request, default_page_limit=DEFAULT_PAGE_LIMIT):
    lang, token_id, token_time, limit = get_params(request, default_page_limit)
    doc_types = request.params.get('t')
    if doc_types is not None:
        doc_types_list = doc_types.split(',')
    else:
        doc_types_list = []
    doc_types_dict = {
        'included': [t for t in doc_types_list if t[0] != '-'],
        'excluded': [t[1] for t in doc_types_list if t[0] == '-']
    }
    return lang, token_id, token_time, limit, doc_types_dict


def get_params(request, default_page_limit=DEFAULT_PAGE_LIMIT):
    lang = request.validated.get('lang')
    token_id = request.validated.get('token_id')
    token_time = request.validated.get('token_time')
    limit = request.validated.get('limit')
    limit = min(
        default_page_limit if limit is None else limit,
        MAX_PAGE_LIMIT)

    return lang, token_id, token_time, limit


def get_changes_of_feed(token_id, token_time, limit, extra_filter=None):
    query = DBSession. \
        query(DocumentChange). \
        order_by(DocumentChange.time.desc(), DocumentChange.change_id)

    # pagination filter
    if token_id is not None and token_time:
        query = query.filter(
            or_(
                DocumentChange.time < token_time,
                and_(
                    DocumentChange.time == token_time,
                    DocumentChange.change_id > token_id)))

    if extra_filter is not None:
        query = query.filter(extra_filter)

    return query.limit(limit).all()


def get_changes_of_personal_feed(
        user_id, token_id, token_time, limit, ignore_admin_changes_filter):
    user = DBSession.query(User). \
        filter(User.id == user_id). \
        options(undefer('has_area_filter')). \
        options(undefer('is_following_users')). \
        first()

    if has_no_custom_filter(user):
        # if no custom filter is set (no area/activity filter and no followed
        # users), return the full/standard feed
        return get_changes_of_feed(
            token_id, token_time, limit, ignore_admin_changes_filter)

    personal_filter = create_personal_filter(user, ignore_admin_changes_filter)

    return get_changes_of_feed(token_id, token_time, limit, personal_filter)


def create_personal_filter(user, ignore_admin_changes_filter):
    """ Create a filter condition for the query to get the changes taking
    the filter preferences of the user into account.
    """
    if user.feed_followed_only:
        # only include changes of followed users
        return create_followed_users_filter(user)

    # filter on area, activity and langs (`and` connected)
    feed_filter = None
    if user.feed_filter_activities or user.has_area_filter or \
       user.feed_filter_langs:
        area_filter = create_area_filter(user)
        activity_filter = create_activity_filter(user)
        lang_filter = create_lang_filter(user)

        filters = []
        if area_filter is not None:
            filters.append(area_filter)
        if activity_filter is not None:
            filters.append(activity_filter)
        if lang_filter is not None:
            filters.append(lang_filter)

        if len(filters) == 1:
            feed_filter = filters[0]
        else:
            feed_filter = and_(f for f in filters)

    if feed_filter is None:
        # if no filter on area or activity, there is no need to check for
        # followed users, because all changes in the feed will be included
        # anyway
        return None

    # filter on followed users
    followed_users_filter = None
    if user.is_following_users:
        followed_users_filter = create_followed_users_filter(user)

    # `or` connect the filter on followed users with the area/activity filter
    if feed_filter is not None and followed_users_filter is not None:
        filter = or_(feed_filter, followed_users_filter)
        return and_(filter, ignore_admin_changes_filter) \
            if ignore_admin_changes_filter else filter
    elif feed_filter is not None:
        return and_(feed_filter, ignore_admin_changes_filter) \
            if ignore_admin_changes_filter else feed_filter
    elif followed_users_filter is not None:
        return followed_users_filter
    else:
        return ignore_admin_changes_filter


def has_no_custom_filter(user):
    has_custom_filter = (
        user.feed_filter_activities or
        user.feed_filter_langs or
        user.has_area_filter or
        user.is_following_users or
        user.feed_followed_only)
    return not has_custom_filter


def create_followed_users_filter(user):
    if not user.is_following_users:
        return None

    followed_users = DBSession. \
        query(func.array_agg(FollowedUser.followed_user_id)). \
        filter(FollowedUser.follower_user_id == user.id). \
        group_by(FollowedUser.follower_user_id). \
        subquery('followed_users')
    return DocumentChange.user_ids.op('&&')(followed_users)


def create_area_filter(user):
    if not user.has_area_filter:
        return None

    filtered_area_ids = DBSession. \
        query(func.array_agg(FilterArea.area_id)). \
        filter(FilterArea.user_id == user.id). \
        group_by(FilterArea.user_id). \
        subquery('filtered_area_ids')
    return DocumentChange.area_ids.op('&&')(filtered_area_ids)


def create_activity_filter(user):
    if not user.feed_filter_activities:
        return None

    return DocumentChange.activities.op('&&')(user.feed_filter_activities)


def create_lang_filter(user):
    if not user.feed_filter_langs:
        return None

    return DocumentChange.langs.op('&&')(user.feed_filter_langs)


def get_changes_of_profile_feed(user_id, token_id, token_time, limit):
    user_exists_query = DBSession.query(User). \
        filter(User.id == user_id). \
        exists()
    user_exists = DBSession.query(user_exists_query).scalar()

    if not user_exists:
        raise HTTPNotFound('user not found')

    user_filter = DocumentChange.user_ids.op('&&')([user_id])

    return get_changes_of_feed(token_id, token_time, limit, user_filter)


def load_feed(changes, lang):
    """ Load the documents referenced in the given changes and build the feed.
    """
    if not changes:
        return {'feed': []}

    documents_to_load = get_documents_to_load(changes)
    documents = load_documents(documents_to_load, lang)

    # only return changes for which the document/user could be loaded
    changes = [
        c for c in changes
        if documents.get(c.user_id) and documents.get(c.document_id)
    ]

    if not changes:
        return {'feed': []}

    last_change = changes[-1]
    pagination_token = '{},{}'.format(
        last_change.change_id,
        urllib_parse.quote_plus(last_change.time.isoformat()))

    return {
        'feed': [
            {
                'id': c.change_id,
                'time': c.time.isoformat(),
                'user': documents[c.user_id],
                'participants': [
                    documents[user_id]
                    for user_id in c.user_ids
                    if user_id != c.user_id and documents.get(user_id)
                ],
                'change_type': c.change_type,
                'document': documents[c.document_id],
                'image1':
                    documents[c.image1_id]
                    if c.image1_id and documents.get(c.image1_id) else None,
                'image2':
                    documents[c.image2_id]
                    if c.image2_id and documents.get(c.image2_id) else None,
                'image3':
                    documents[c.image3_id]
                    if c.image3_id and documents.get(c.image3_id) else None,
                'more_images': c.more_images
            }
            for c in changes
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


def get_ignore_admin_entries_filter(request):
    account_id = request.registry.feed_admin_user_account_id
    if account_id is None:
        return None

    return DocumentChange.user_id != account_id
