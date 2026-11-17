"""Tests of the script giving the comment topics their new title and tags."""

import datetime
from unittest.mock import MagicMock

import pytest

from c2corg_api.models.document_topic import DocumentTopic
from c2corg_api.models.outing import Outing, OutingLocale
from c2corg_api.scripts.forum.retitle_topics import (
    FIRST_INTERIM_TOPIC_ID,
    retitle,
    topics_to_retitle,
)


@pytest.fixture
def outing(session):
    """An outing with 2 locales: an older topic in fr, an interim one in en."""
    outing = Outing(
        activities=['skitouring'],
        date_start=datetime.date(2026, 11, 2),
        date_end=datetime.date(2026, 11, 2),
        locales=[
            OutingLocale(
                lang='fr',
                title='Mont Granier',
                document_topic=DocumentTopic(topic_id=1000),
            ),
            OutingLocale(
                lang='en',
                title='Mont Granier',
                document_topic=DocumentTopic(topic_id=FIRST_INTERIM_TOPIC_ID + 1),
            ),
        ],
    )
    session.add(outing)
    session.flush()
    return outing


def _topic_ids(start_after=0, everything=False, limit=None):
    """Give the topic ids the script would take."""
    return [
        topic_id for topic_id, _, _ in topics_to_retitle(start_after, everything, limit)
    ]


def test_interim_topics_by_default(outing):
    """Only the topics with the interim titles, unless all are asked."""
    assert _topic_ids() == [FIRST_INTERIM_TOPIC_ID + 1]
    assert _topic_ids(everything=True)[-2:] == [1000, FIRST_INTERIM_TOPIC_ID + 1]
    assert _topic_ids(start_after=FIRST_INTERIM_TOPIC_ID + 1) == []


def _client(tags):
    """A forum client whose topic has the given tags."""
    client = MagicMock()
    client.client._get.return_value = {
        'title': '1_en · Outing · Mont Granier · 2026-11-02',
        'tags': tags,
        'post_stream': {'posts': [{'id': 50, 'post_number': 1}]},
    }
    return client


def test_dry_run(outing):
    """Without --apply, nothing is sent to the forum."""
    client = _client([])
    topic_id, document, locale = next(topics_to_retitle(0, False, None))
    retitle(client, topic_id, document, locale, apply=False, first_post=True)
    client.client.update_topic.assert_not_called()
    client.client.update_post.assert_not_called()


def test_apply(outing):
    """The title and tags change, the tags of the moderators stay."""
    client = _client([{'id': 7, 'name': 'topo', 'slug': 'topo'}])
    topic_id, document, locale = next(topics_to_retitle(0, False, None))
    retitle(client, topic_id, document, locale, apply=True, first_post=False)
    client.client.update_topic.assert_called_once_with(
        f'/t/-/{topic_id}.json',
        title='Mont Granier · 2026-11-02',
        **{'tags[]': ['en', 'sortie', 'topo']},
    )
    client.client.update_post.assert_not_called()

    retitle(client, topic_id, document, locale, apply=True, first_post=True)
    client.client.update_post.assert_called_once()
    assert client.client.update_post.call_args.args[0] == 50
