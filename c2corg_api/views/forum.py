import html
import logging
import threading
from functools import partial

from pydiscourse.exceptions import DiscourseClientError

from c2corg_api.httpexceptions import (
    HTTPInternalServerError,
    HTTPServiceUnavailable,
)
from c2corg_api.models import DBSession
from c2corg_api.models.association import Association, association_keys_for_types
from c2corg_api.models.cache_version import update_cache_version_direct
from c2corg_api.models.common import document_types
from c2corg_api.models.document import Document, DocumentLocale
from c2corg_api.models.document_topic import DocumentTopic
from c2corg_api.models.user import User
from c2corg_api.schemas.base import Schema, body_validator
from c2corg_api.schemas.types import Int, Str
from c2corg_api.search.notify_sync import run_on_successful_transaction
from c2corg_api.security.discourse_client import get_discourse_client
from c2corg_api.views.forum_labels import (
    COMMENTS_LABELS,
    DOCUMENT_TYPE_LABELS,
    WAYPOINT_TYPE_LABELS,
)
from c2corg_api.views.resource import write

log = logging.getLogger(__name__)

# Discourse's max_topic_title_length (its default)
TITLE_MAX_LENGTH = 255
TITLE_SEPARATOR = ' · '

DOCUMENT_TYPE_NAMES = {
    document_types.AREA_TYPE: 'area',
    document_types.ARTICLE_TYPE: 'article',
    document_types.BOOK_TYPE: 'book',
    document_types.IMAGE_TYPE: 'image',
    document_types.MAP_TYPE: 'map',
    document_types.OUTING_TYPE: 'outing',
    document_types.ROUTE_TYPE: 'route',
    document_types.WAYPOINT_TYPE: 'waypoint',
    document_types.XREPORT_TYPE: 'xreport',
}

# too vague to name a waypoint: the generic 'waypoint' label is used instead
VAGUE_WAYPOINT_TYPES = {'misc', 'virtual'}


class TopicCreateSchema(Schema):
    document_id: Int
    lang: Str()


def validate_topic_create(request, **kwargs):
    document_id = request.validated['document_id']
    lang = request.validated['lang']

    locale = (
        DBSession.query(DocumentLocale)
        .filter(DocumentLocale.document_id == document_id)
        .filter(DocumentLocale.lang == lang)
        .one_or_none()
    )
    if locale is None:
        request.errors.add('body', f'{document_id}/{lang}', 'Document not found')
        return
    request.validated['locale'] = locale

    document = (
        DBSession.query(Document)
        .filter(Document.document_id == document_id)
        .one_or_none()
    )
    if document is None:
        request.errors.add('body', f'{document_id}/{lang}', 'Document not found')
        return
    request.validated['document'] = document

    # the profiles have no comments: the UI does not show them
    if document.type == document_types.USERPROFILE_TYPE:
        request.errors.add('body', f'{document_id}_{lang}', 'No comments for a profile')
        return

    if locale.topic_id is not None:
        request.errors.add(
            'body',
            f'{document_id}_{lang}',
            'Topic already exists',
            topic_id=locale.topic_id,
        )


def _deshout(text):
    """Write an all-capitals text in sentence case."""
    # Discourse would rewrite a shouted title anyway (title_prevent_shouting)
    if text.isupper():
        return text[:1].upper() + text[1:].lower()
    return text


def _type_label(document, lang):
    """Name the type of the document in the given language."""
    labels = DOCUMENT_TYPE_LABELS.get(lang, DOCUMENT_TYPE_LABELS['en'])
    if document.type == document_types.WAYPOINT_TYPE:
        waypoint_type = document.waypoint_type
        if waypoint_type not in VAGUE_WAYPOINT_TYPES:
            waypoint_labels = WAYPOINT_TYPE_LABELS.get(lang, WAYPOINT_TYPE_LABELS['en'])
            if waypoint_type in waypoint_labels:
                return waypoint_labels[waypoint_type]
    return labels.get(DOCUMENT_TYPE_NAMES.get(document.type))


def _date(document):
    """Give the date shown in the title of the document, if any."""
    if document.type == document_types.OUTING_TYPE:
        return document.date_start
    if document.type == document_types.XREPORT_TYPE:
        return document.date
    return None


def legacy_topic_title(locale):
    """Give the title of the comment topics before November 2026."""
    return f'{locale.document_id}_{locale.lang}'


def _document_title(locale):
    """Give the title of a document locale, as the topic shows it."""
    title = _deshout((locale.title or '').strip())
    title_prefix = getattr(locale, 'title_prefix', None)
    if title_prefix and title:
        title = f'{_deshout(title_prefix.strip())} : {title}'
    return title


def topic_title(document, locale):
    """Give the title of the comment topic of a document locale."""
    # '1966268_fr · Sortie · Mont Blanc par les Grands Mulets · 2026-11-02'
    # The id comes first: titles stay unique (Discourse refuses duplicates) and the
    # topics can still be found by the id, as the older ones.
    title = _document_title(locale)

    date = _date(document)
    # no type label for some types (profiles)
    head = [
        part
        for part in [legacy_topic_title(locale), _type_label(document, locale.lang)]
        if part
    ]
    tail = [date.isoformat()] if date else []

    # only the title of the document is shortened, never the id or the date
    room = TITLE_MAX_LENGTH - len(TITLE_SEPARATOR.join([*head, '', *tail]))
    if len(title) > room:
        title = title[: room - 1].rstrip() + '…'

    return TITLE_SEPARATOR.join(part for part in [*head, title, *tail] if part)


def first_post_content(document, locale):
    """Give the first post of the comment topic of a document locale."""
    # 'Commentaires : Sortie · <a href=".../outings/1966268/fr">Mont Blanc…</a> ·
    # 2026-11-02'
    document_type = association_keys_for_types[document.type]
    path = f'/{document_type}/{locale.document_id}/{locale.lang}'
    link = (
        f'<a href="https://www.camptocamp.org{path}">'
        f'{html.escape(_document_title(locale) or path)}</a>'
    )
    parts = [_type_label(document, locale.lang), link]
    if document.type == document_types.OUTING_TYPE:
        parts.append(document.date_start.isoformat())
    comments = COMMENTS_LABELS.get(locale.lang, COMMENTS_LABELS['en'])
    # French typography: a space before the colon
    colon = ' : ' if locale.lang == 'fr' else ': '
    return comments + colon + TITLE_SEPARATOR.join(part for part in parts if part)


def topic_texts(document):
    """Give the title and first post of the comment topics, by topic id."""
    topic_ids = dict(
        DBSession.query(DocumentTopic.document_locale_id, DocumentTopic.topic_id)
        .join(DocumentLocale, DocumentLocale.id == DocumentTopic.document_locale_id)
        .filter(DocumentLocale.document_id == document.document_id)
        .all()
    )
    return {
        topic_ids[locale.id]: (
            topic_title(document, locale),
            first_post_content(document, locale),
        )
        for locale in document.locales
        if locale.id in topic_ids
    }


def rename_topics(request, document, old_texts):
    """Update the comment topics whose title or first post changed."""
    # old_texts: topic_texts(document) before the update. The older topics, titled
    # `{id}_{lang}`, are updated too when the document title changes.
    if not old_texts:
        return
    for locale in document.locales:
        if hasattr(locale, 'title_prefix'):
            # set by an SQL update (check_title_prefix): the loaded value is stale
            DBSession.expire(locale, ['title_prefix'])

    changes = {
        topic_id: (
            title if title != old_texts[topic_id][0] else None,
            content if content != old_texts[topic_id][1] else None,
        )
        for topic_id, (title, content) in topic_texts(document).items()
        if topic_id in old_texts and (title, content) != old_texts[topic_id]
    }
    if not changes:
        return

    client = get_discourse_client(request.registry.settings)
    if not client.enabled:
        return
    # never slows down nor fails the edit: the forum is called once it is saved
    run_on_successful_transaction(
        partial(in_background, partial(_update_topics, client, changes))
    )


def in_background(operation):
    """Run an operation in a thread of its own."""
    threading.Thread(target=operation, daemon=True).start()


def _update_topics(client, changes):
    """Give the topics their new title and first post in Discourse."""
    # changes: (title, content) by topic id, None for what is unchanged
    for topic_id, (title, content) in changes.items():
        try:
            if title is not None:
                client.client.update_topic(f'/t/-/{topic_id}.json', title=title)
            if content is not None:
                posts = client.client.topic_posts(topic_id)['post_stream']['posts']
                first_post = next(p for p in posts if p['post_number'] == 1)
                client.client.update_post(first_post['id'], content)
        except Exception:
            # the topic keeps its former title or first post
            log.warning(f'Updating the forum topic {topic_id} failed', exc_info=True)


# only collection_post: it creates the topic in Discourse
@write(
    validators=[body_validator(TopicCreateSchema), validate_topic_create],
    permission='authenticated',
    json=False,
)
def create_topic(request):
    settings = request.registry.settings

    client = get_discourse_client(settings)
    if not client.enabled:
        raise HTTPServiceUnavailable('The forum is disabled')

    locale = request.validated['locale']
    document = request.validated['document']
    content = first_post_content(document, locale)

    category = settings['discourse.category']
    # category could be id or name
    try:
        category = int(category)
    except ValueError:
        pass  # a name: use it as it is

    try:
        try:
            response = client.client.create_post(
                content, title=topic_title(document, locale), category_id=category
            )
        except DiscourseClientError as e:
            # a title Discourse refuses (too short, shouting...): the id still works
            if e.response is None or e.response.status_code != 422:
                raise
            log.warning(f'Discourse refused the title of the topic: {e!s}')
            response = client.client.create_post(
                content, title=legacy_topic_title(locale), category_id=category
            )
    except Exception as e:
        log.error(f'Error with Discourse: {e!s}', exc_info=True)
        raise HTTPInternalServerError('Error with Discourse') from e

    if 'topic_id' in response:
        topic_id = response['topic_id']

        document_topic = DocumentTopic(topic_id=topic_id)
        locale.document_topic = document_topic
        update_cache_version_direct(locale.document_id)
        DBSession.flush()

        if locale.type == document_types.OUTING_TYPE:
            try:
                watch_by_participants(client, locale, topic_id)
            except Exception:
                log.error(
                    f'Watching by the participants of outing {locale.document_id} '
                    'failed',
                    exc_info=True,
                )

    return response


def watch_by_participants(client, locale, topic_id):
    """Make the participants of an outing watch its comment topic."""
    # They are notified of each comment, and of nothing while the topic is empty
    # (an invitation used to notify them as soon as the topic was created).
    participants = (
        DBSession.query(User.forum_username)
        .join(Association, Association.parent_document_id == User.id)
        .filter(Association.child_document_id == locale.document_id)
        .group_by(User.forum_username)
    )

    for (forum_username,) in participants:
        try:
            client.watch_topic(forum_username, topic_id)
        except Exception:
            log.error(
                f'Watching by forum user {forum_username} of topic {topic_id} failed',
                exc_info=True,
            )
