"""Give the comment topics in the forum the title and tags of the new ones."""

# Usage: python -m c2corg_api.scripts.forum.retitle_topics [options] [config_uri]
#
# Without --apply, only prints what would change. By default, only the topics created
# with the interim `{id}_{lang} · {type} · …` titles (November 9 to 17, 2026); --all
# takes every comment topic. Resume with --start-after <last topic id printed>.
#
# Each topic costs 2 requests to Discourse (3 with --first-post), and the admin API
# allows 60 per minute by default: --delay keeps under it.

import argparse
import logging
import sys
import time

from pydiscourse.exceptions import DiscourseClientError
from sqlalchemy import engine_from_config

from c2corg_api.config import get_appsettings
from c2corg_api.models import DBSession
from c2corg_api.models.document import Document, DocumentLocale
from c2corg_api.models.document_topic import DocumentTopic
from c2corg_api.security.discourse_client import get_discourse_client
from c2corg_api.views.forum import (
    first_post_content,
    topic_tags,
    topic_titles,
    update_topic_title,
)

log = logging.getLogger(__name__)

# the first topic titled `{id}_{lang} · {type} · …` (v6.31.0, 2026-11-09)
FIRST_INTERIM_TOPIC_ID = 371254


def parse_args(argv):
    """Read the options of the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config_uri', nargs='?', default='production.ini')
    parser.add_argument('--apply', action='store_true', help='change the topics')
    parser.add_argument('--all', action='store_true', help='every comment topic')
    parser.add_argument(
        '--first-post', action='store_true', help='also rewrite the first post'
    )
    parser.add_argument('--start-after', type=int, default=0, metavar='TOPIC_ID')
    parser.add_argument('--limit', type=int, help='at most this number of topics')
    parser.add_argument(
        '--delay', type=float, default=2.0, help='seconds between topics (default 2)'
    )
    return parser.parse_args(argv)


def topics_to_retitle(start_after, everything, limit):
    """Give the (topic id, document, locale) of the topics to retitle, in order."""
    first = start_after + 1
    if not everything:
        first = max(first, FIRST_INTERIM_TOPIC_ID)
    query = (
        DBSession.query(DocumentTopic.topic_id, DocumentLocale)
        .join(DocumentLocale, DocumentLocale.id == DocumentTopic.document_locale_id)
        .filter(DocumentTopic.topic_id >= first)
        .order_by(DocumentTopic.topic_id)
    )
    if limit:
        query = query.limit(limit)
    for topic_id, locale in query.yield_per(500):
        document = DBSession.get(Document, locale.document_id)
        yield topic_id, document, locale


def retitle(client, topic_id, document, locale, apply, first_post):
    """Give a topic its title and tags, and maybe its first post; say what changes."""
    topic = client.client._get(f'/t/{topic_id}.json')
    titles = topic_titles(document, locale)
    # the tags set by the moderators stay
    tags = list(dict.fromkeys([*topic_tags(document, locale), *_tag_names(topic)]))
    print(f'{topic_id}: {topic["title"]!r} -> {titles[0]!r} {tags}', flush=True)
    if not apply:
        return
    update_topic_title(client, topic_id, titles, **{'tags[]': tags})
    if first_post:
        first = topic['post_stream']['posts'][0]
        client.client.update_post(first['id'], first_post_content(document, locale))


def _tag_names(topic):
    """Give the names of the tags of a topic."""
    # recent Discourse gives tags as objects ({id, name, slug}), older ones as names
    tags = topic.get('tags') or []
    return [tag['name'] if isinstance(tag, dict) else tag for tag in tags]


def main(argv=None):
    """Retitle the comment topics."""
    args = parse_args(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(level=logging.WARNING)
    settings = get_appsettings(args.config_uri)
    DBSession.configure(bind=engine_from_config(settings, 'sqlalchemy.'))
    client = get_discourse_client(settings)
    if not client.enabled:
        sys.exit('The forum is disabled')

    done = failed = 0
    for topic_id, document, locale in topics_to_retitle(
        args.start_after, args.all, args.limit
    ):
        try:
            retitle(client, topic_id, document, locale, args.apply, args.first_post)
            done += 1
        except DiscourseClientError as e:
            # a topic deleted in the forum (404), ...: the others go on
            print(f'{topic_id}: failed: {e!s}', flush=True)
            failed += 1
        if args.apply:
            time.sleep(args.delay)
    print(
        f'{done} topics {"retitled" if args.apply else "to retitle"}, {failed} failed'
    )


if __name__ == '__main__':
    main()
