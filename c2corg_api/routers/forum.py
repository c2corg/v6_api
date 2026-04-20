"""
FastAPI Forum router.

Provides:
  - ``/v2/forum/private-messages/unread-count`` — unread PM count
  - ``/v2/forum/topics``                        — create a Discourse topic

Mirrors ``c2corg_api.views.forum``.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from c2corg_api.database import get_db
from c2corg_api.models.association import Association, association_keys_for_types
from c2corg_api.models.cache_version import update_cache_version_direct
from c2corg_api.models.common import document_types
from c2corg_api.models.document import Document, DocumentLocale
from c2corg_api.models.document_topic import DocumentTopic
from c2corg_api.models.user import User
from c2corg_api.security.discourse_client import get_discourse_client
from c2corg_api.security.fastapi_security import get_current_user

log = logging.getLogger(__name__)

router = APIRouter(prefix='/v2/forum', tags=['forum'])

# Module-level settings cache — set once by ``configure_forum_router``.
_settings: dict = {}


def configure_forum_router(settings: dict) -> None:
    """Called once at startup to capture Discourse settings."""
    global _settings
    _settings = settings


# ──────────────────────────────────────────────────────────────
# GET /v2/forum/private-messages/unread-count
# ──────────────────────────────────────────────────────────────


@router.get('/private-messages/unread-count')
def get_unread_count(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Return unread private-message count from Discourse."""
    client = get_discourse_client(_settings)
    d_username = client.get_username(user.id)
    messages = client.client.private_messages_unread(d_username)

    count = len(messages['topic_list']['topics'])
    link = '%s/users/%s/messages' % (client.discourse_public_url, d_username)

    return {link: link, count: count}


# ──────────────────────────────────────────────────────────────
# POST /v2/forum/topics
# ──────────────────────────────────────────────────────────────


class TopicCreateSchema(BaseModel):
    document_id: int
    lang: str


@router.post('/topics')
def create_topic(
    body: TopicCreateSchema,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a Discourse topic for a document locale."""
    document_id = body.document_id
    lang = body.lang

    # Validate locale exists
    locale = (
        db.query(DocumentLocale)
        .filter(DocumentLocale.document_id == document_id)
        .filter(DocumentLocale.lang == lang)
        .one_or_none()
    )
    if locale is None:
        raise HTTPException(
            status_code=400,
            detail={
                'status': 'error',
                'errors': [
                    {
                        'location': 'body',
                        'name': '{}/{}'.format(document_id, lang),
                        'description': 'Document not found',
                    }
                ],
            },
        )

    # Validate document exists
    document = (
        db.query(Document).filter(Document.document_id == document_id).one_or_none()
    )
    if document is None:
        raise HTTPException(
            status_code=400,
            detail={
                'status': 'error',
                'errors': [
                    {
                        'location': 'body',
                        'name': '{}/{}'.format(document_id, lang),
                        'description': 'Document not found',
                    }
                ],
            },
        )

    # Check topic doesn't already exist
    if locale.topic_id is not None:
        raise HTTPException(
            status_code=400,
            detail={
                'status': 'error',
                'errors': [
                    {
                        'location': 'body',
                        'name': '{}_{}'.format(document_id, lang),
                        'description': 'Topic already exists',
                        'topic_id': locale.topic_id,
                    }
                ],
            },
        )

    # Build content
    document_type = association_keys_for_types[document.type]
    document_path = '/{}/{}/{}'.format(document_type, locale.document_id, locale.lang)
    content = '<a href="https://www.camptocamp.org{}">{}</a>'.format(
        document_path, locale.title or document_path
    )

    category = _settings.get('discourse.category', '')
    try:
        category = int(category)
    except Exception:
        pass

    client = get_discourse_client(_settings)
    try:
        title = '{}_{}'.format(locale.document_id, locale.lang)
        response = client.client.create_post(content, title=title, category=category)
    except Exception as e:
        log.error('Error with Discourse: {}'.format(str(e)), exc_info=True)
        raise HTTPException(status_code=500, detail='Error with Discourse')

    if 'topic_id' in response:
        topic_id = response['topic_id']

        document_topic = DocumentTopic(topic_id=topic_id)
        locale.document_topic = document_topic
        update_cache_version_direct(locale.document_id)
        db.flush()

        if locale.type == document_types.OUTING_TYPE:
            try:
                _invite_participants(client, locale, topic_id, db)
            except Exception:
                log.error(
                    'Inviting participants of outing {} failed'.format(
                        locale.document_id
                    ),
                    exc_info=True,
                )

    return response


def _invite_participants(client, locale, topic_id, db):
    """Invite outing participants to the Discourse topic."""
    participants = (
        db.query(User.forum_username)
        .join(Association, Association.parent_document_id == User.id)
        .filter(Association.child_document_id == locale.document_id)
        .group_by(User.forum_username)
    )

    for (forum_username,) in participants:
        try:
            client.client.invite_user_to_topic_by_username(forum_username, topic_id)
        except Exception:
            log.error(
                'Inviting forum user {} in topic {} failed'.format(
                    forum_username, topic_id
                ),
                exc_info=True,
            )
