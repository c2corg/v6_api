"""
Feed query and formatting helpers.

Extracted from ``c2corg_api.views.feed`` so that the FastAPI router
has no dependency on ``views/``.
"""

from collections import defaultdict
from urllib import parse as urllib_parse

from fastapi import HTTPException
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import undefer

from c2corg_api.routers.helpers._db_compat import resolve_db
from c2corg_api.models.feed import DocumentChange, FilterArea, FollowedUser
from c2corg_api.models.image import IMAGE_TYPE
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.routers.helpers.document_listings import get_documents_for_ids
from c2corg_api.routers.helpers.document_schemas import document_configs

DEFAULT_PAGE_LIMIT = 10
MAX_PAGE_LIMIT = 50


def get_changes_of_feed(token_id, token_time, limit, extra_filter=None):
    query = (
        resolve_db(None)
        .query(DocumentChange)
        .order_by(DocumentChange.time.desc(), DocumentChange.change_id)
    )

    if token_id is not None and token_time:
        query = query.filter(
            or_(
                DocumentChange.time < token_time,
                and_(
                    DocumentChange.time == token_time,
                    DocumentChange.change_id > token_id,
                ),
            )
        )

    if extra_filter is not None:
        query = query.filter(extra_filter)

    return query.limit(limit).all()


def get_changes_of_personal_feed(
    user_id, token_id, token_time, limit, ignore_admin_changes_filter
):
    user = (
        resolve_db(None)
        .query(User)
        .filter(User.id == user_id)
        .options(undefer(User.has_area_filter))
        .options(undefer(User.is_following_users))
        .first()
    )

    if _has_no_custom_filter(user):
        return get_changes_of_feed(
            token_id, token_time, limit, ignore_admin_changes_filter
        )

    personal_filter = _create_personal_filter(user, ignore_admin_changes_filter)
    return get_changes_of_feed(token_id, token_time, limit, personal_filter)


def get_changes_of_profile_feed(user_id, token_id, token_time, limit):
    user_exists_query = resolve_db(None).query(User).filter(User.id == user_id).exists()
    user_exists = resolve_db(None).query(user_exists_query).scalar()

    if not user_exists:
        raise HTTPException(status_code=404, detail='user not found')

    user_filter = DocumentChange.user_ids.op('&&')([user_id])
    return get_changes_of_feed(token_id, token_time, limit, user_filter)


def load_feed(changes, lang):
    """Load referenced documents and build the feed response."""
    if not changes:
        return {'feed': []}

    documents_to_load = _get_documents_to_load(changes)
    documents = _load_documents(documents_to_load, lang)

    changes = [
        c for c in changes if documents.get(c.user_id) and documents.get(c.document_id)
    ]

    if not changes:
        return {'feed': []}

    last_change = changes[-1]
    pagination_token = '{},{}'.format(
        last_change.change_id, urllib_parse.quote_plus(last_change.time.isoformat())
    )

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
                'image1': documents[c.image1_id]
                if c.image1_id and documents.get(c.image1_id)
                else None,
                'image2': documents[c.image2_id]
                if c.image2_id and documents.get(c.image2_id)
                else None,
                'image3': documents[c.image3_id]
                if c.image3_id and documents.get(c.image3_id)
                else None,
                'more_images': c.more_images,
            }
            for c in changes
        ],
        'pagination_token': pagination_token,
    }


# ── private helpers ──────────────────────────────────────────


def _has_no_custom_filter(user):
    return not (
        user.feed_filter_activities
        or user.feed_filter_langs
        or user.has_area_filter
        or user.is_following_users
        or user.feed_followed_only
    )


def _create_personal_filter(user, ignore_admin_changes_filter):
    if user.feed_followed_only:
        return _create_followed_users_filter(user)

    feed_filter = None
    if user.feed_filter_activities or user.has_area_filter or user.feed_filter_langs:
        area_filter = _create_area_filter(user)
        activity_filter = _create_activity_filter(user)
        lang_filter = _create_lang_filter(user)

        filters = [
            f for f in (area_filter, activity_filter, lang_filter) if f is not None
        ]

        if len(filters) == 1:
            feed_filter = filters[0]
        elif filters:
            feed_filter = and_(*filters)

    if feed_filter is None:
        return None

    followed_users_filter = None
    if user.is_following_users:
        followed_users_filter = _create_followed_users_filter(user)

    if feed_filter is not None and followed_users_filter is not None:
        combined = or_(feed_filter, followed_users_filter)
        return (
            and_(combined, ignore_admin_changes_filter)
            if ignore_admin_changes_filter is not None
            else combined
        )
    elif feed_filter is not None:
        return (
            and_(feed_filter, ignore_admin_changes_filter)
            if ignore_admin_changes_filter is not None
            else feed_filter
        )
    elif followed_users_filter is not None:
        return followed_users_filter
    else:
        return ignore_admin_changes_filter


def _create_followed_users_filter(user):
    if not user.is_following_users:
        return None
    followed_users = (
        resolve_db(None)
        .query(func.array_agg(FollowedUser.followed_user_id))
        .filter(FollowedUser.follower_user_id == user.id)
        .group_by(FollowedUser.follower_user_id)
        .scalar_subquery()
    )
    return DocumentChange.user_ids.op('&&')(followed_users)


def _create_area_filter(user):
    if not user.has_area_filter:
        return None
    filtered_area_ids = (
        resolve_db(None)
        .query(func.array_agg(FilterArea.area_id))
        .filter(FilterArea.user_id == user.id)
        .group_by(FilterArea.user_id)
        .scalar_subquery()
    )
    return DocumentChange.area_ids.op('&&')(filtered_area_ids)


def _create_activity_filter(user):
    if not user.feed_filter_activities:
        return None
    return DocumentChange.activities.op('&&')(user.feed_filter_activities)


def _create_lang_filter(user):
    if not user.feed_filter_langs:
        return None
    return DocumentChange.langs.op('&&')(user.feed_filter_langs)


def _get_documents_to_load(changes):
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


def _load_documents(documents_to_load, lang):
    documents = {}
    for document_type, document_ids in documents_to_load.items():
        document_config = document_configs[document_type]
        docs = get_documents_for_ids(document_ids, lang, document_config).get(
            'documents'
        )
        for doc in docs:
            documents[doc['document_id']] = doc
    return documents
