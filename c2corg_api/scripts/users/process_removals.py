"""Remove the accounts of the validated removal requests.

A request (see views/user_removal.py) is processed once it is validated by a
moderator of the topoguide and by one of the forum, its date is past, and a
delay has elapsed since its last validation (to leave time to cancel a
validation made by mistake).

The script only lists the requests to process, with what would be removed,
unless `--execute` is given. `--id` limits it to some requests:

    python -m c2corg_api.scripts.users.process_removals
    python -m c2corg_api.scripts.users.process_removals --id 12
    python -m c2corg_api.scripts.users.process_removals --id 12 --execute

For each request:
- spam: the documents the user alone contributed to (outings, reports,
  articles and images) are deleted for good (not kept to be restored), their
  comment topics closed and unlisted, and the account of the forum is deleted
  with its posts;
- else: the account of the forum is merged into the target one;
- then the account of the topoguide is merged into the target one, as with
  scripts/users/merge.py.

Each request is locked while it is processed, and checked again once locked: a
validation cancelled meanwhile stops it, and two runs at once never process the
same request. Nothing is done when the forum is disabled (`discourse.enabled`):
its account would stay.

To check on a test forum before the first run in production:
- the forum account is found again by its external id when the request is
  processed (forum_id is only kept as a record): if the user logs in between
  the forum merge and a re-run, SSO creates a new forum account, merged then;
- Discourse merges the accounts in a background job: the answer of the merge
  does not prove it is finished;
- Discourse refuses to delete a user whose posts are older than its
  `delete_user_max_post_age` setting: a spam request then fails on every run,
  until the account is handled in the forum by hand.
"""

import argparse
import datetime
import logging
import os
import sys
from types import SimpleNamespace

from sqlalchemy import engine_from_config
from sqlalchemy.exc import OperationalError
from sqlalchemy.sql.expression import and_, exists

from c2corg_api.config import get_appsettings
from c2corg_api.models import DBSession, commit_or_rollback
from c2corg_api.models.account_removal import (
    ACTION_DONE,
    DEFAULT_GRACE_HOURS,
    REASON_SPAM,
    AccountRemovalRequest,
    is_ready,
    log_action,
)
from c2corg_api.models.article import ARTICLE_TYPE
from c2corg_api.models.document import Document, DocumentLocale
from c2corg_api.models.document_history import DocumentVersion, HistoryMetaData
from c2corg_api.models.document_topic import DocumentTopic
from c2corg_api.models.image import IMAGE_TYPE
from c2corg_api.models.outing import OUTING_TYPE
from c2corg_api.models.user import User
from c2corg_api.models.xreport import XREPORT_TYPE
from c2corg_api.scripts.users.merge import merge_user_accounts
from c2corg_api.search import get_queue_config
from c2corg_api.security.discourse_client import get_discourse_client
from c2corg_api.views.document_delete import _delete
from c2corg_api.views.forum import set_topics_hidden

log = logging.getLogger(__name__)

# the documents that may be deleted with a spammer: the types a user creates
# alone (a waypoint or a route is also used by the other contributors)
PURGED_TYPES = [OUTING_TYPE, XREPORT_TYPE, ARTICLE_TYPE, IMAGE_TYPE]


def find_ready_requests(now, grace_hours=DEFAULT_GRACE_HOURS, ids=None):
    """Return the requests validated by both sides, which can be processed."""
    today = now.date()
    limit = now - datetime.timedelta(hours=grace_hours)
    query = (
        DBSession.query(AccountRemovalRequest)
        .filter(
            AccountRemovalRequest.done_at.is_(None),
            AccountRemovalRequest.cancelled_at.is_(None),
            AccountRemovalRequest.topoguide_validated_by.is_not(None),
            AccountRemovalRequest.forum_validated_by.is_not(None),
            AccountRemovalRequest.executable_after <= today,
            AccountRemovalRequest.topoguide_validated_at <= limit,
            AccountRemovalRequest.forum_validated_at <= limit,
        )
        .order_by(AccountRemovalRequest.id)
    )
    if ids is not None:
        query = query.filter(AccountRemovalRequest.id.in_(ids))
    return query.all()


def find_purged_documents(user_id):
    """Return the (id, type) of the documents only this user contributed to."""
    by_others = (
        exists()
        .where(
            and_(
                DocumentVersion.document_id == Document.document_id,
                HistoryMetaData.id == DocumentVersion.history_metadata_id,
                HistoryMetaData.user_id != user_id,
            )
        )
        .correlate(Document)
    )
    by_user = (
        exists()
        .where(
            and_(
                DocumentVersion.document_id == Document.document_id,
                HistoryMetaData.id == DocumentVersion.history_metadata_id,
                HistoryMetaData.user_id == user_id,
            )
        )
        .correlate(Document)
    )
    return (
        DBSession.query(Document.document_id, Document.type)
        .filter(Document.type.in_(PURGED_TYPES), by_user, ~by_others)
        .order_by(Document.document_id)
        .all()
    )


def purge_contributions(user_id, settings, queue_config):
    """Delete the documents only this user contributed to.

    Return the ids of the documents and of their comment topics.
    """
    # `_delete` is the deletion of the views: it only reads the registry. Not
    # kept to be restored (keep=False): the spam goes for good, and the request
    # has no user.
    request = SimpleNamespace(
        registry=SimpleNamespace(settings=settings, queue_config=queue_config)
    )
    documents = find_purged_documents(user_id)
    topic_ids = [
        topic_id
        for (topic_id,) in DBSession.query(DocumentTopic.topic_id)
        .join(DocumentLocale, DocumentLocale.id == DocumentTopic.document_locale_id)
        .filter(DocumentLocale.document_id.in_([d for d, _ in documents]))
    ]
    for document_id, document_type in documents:
        print(f'Deleting the document {document_id} ({document_type})...')
        _delete(request, document_id, document_type, keep=False)
    return [d for d, _ in documents], topic_ids


def _is_not_found(error):
    response = getattr(error, 'response', None)
    return response is not None and response.status_code == 404


def _remove_forum_account(client, removal):
    """Merge (or delete for a spammer) the account of the forum; say which."""
    try:
        if removal.reason == REASON_SPAM:
            print('Deleting the forum account and its posts...')
            client.delete_user(removal.user_id, delete_posts=True)
            return 'deleted'
        print('Merging the forum account...')
        client.merge_user(removal.user_id, removal.target_forum_id)
        return 'merged'
    except Exception as e:
        # already removed by a previous run, which failed afterwards
        if not _is_not_found(e):
            raise
        print('The forum account does not exist anymore.')
        return 'not_found'


class ForumDisabledError(Exception):
    """The forum is disabled: its account cannot be removed."""


def _lock(removal_id):
    # locked until the end of the transaction; NOWAIT: a request another run
    # is processing is skipped (OperationalError), not waited for
    return (
        DBSession.query(AccountRemovalRequest)
        .filter(AccountRemovalRequest.id == removal_id)
        .with_for_update(nowait=True)
        .one()
    )


def process_removal(
    removal_id, settings, queue_config, grace_hours=DEFAULT_GRACE_HOURS
):
    """Remove the account of a request; return False if it is not ready anymore."""
    client = get_discourse_client(settings)
    if not client.enabled:
        raise ForumDisabledError('The forum is disabled: its account would stay')

    topic_ids = []
    with commit_or_rollback(DBSession):
        removal = _lock(removal_id)
        # read again once locked: a validation may have been cancelled since
        # the list of the ready requests was made
        if not is_ready(removal, datetime.datetime.now(datetime.UTC), grace_hours):
            print(f'The request #{removal_id} is not ready anymore.')
            return False

        user_id = removal.user_id
        if DBSession.get(User, user_id) is None:
            # merged by hand since the request
            print(f'The account {user_id} does not exist anymore.')
        elif DBSession.get(User, removal.target_user_id) is None:
            raise ValueError(
                f'The target account {removal.target_user_id} does not exist'
            )

        # the forum first: if a later step fails, the transaction is rolled
        # back and the next run does it again (the forum account is then
        # already gone, see _remove_forum_account)
        forum = _remove_forum_account(client, removal)

        # what was removed, kept in the history of the request
        details = {'forum': forum, 'topoguide': 'not_found'}
        if DBSession.get(User, user_id) is not None:
            if removal.reason == REASON_SPAM:
                document_ids, topic_ids = purge_contributions(
                    user_id, settings, queue_config
                )
                details['documents'] = document_ids
            merge_user_accounts(user_id, removal.target_user_id, queue_config)
            details['topoguide'] = 'merged'
        removal.done_at = datetime.datetime.now(datetime.UTC)
        log_action(removal, ACTION_DONE, None, **details)

    # the comment topics of the purged documents, once it is all saved
    set_topics_hidden(client, topic_ids, True)
    return True


def describe(removal):
    return (
        f'#{removal.id}: {removal.reason}, account {removal.user_id} '
        f'({removal.user_name}/{removal.user_forum_username}) -> '
        f'{removal.target_user_id} (forum {removal.target_forum_id})'
    )


def _forum_account(client, removal):
    """Describe the forum account to remove; only reads the forum."""
    try:
        forum_id = client.get_userid(removal.user_id)
    except Exception as e:
        if _is_not_found(e):
            return 'none (already removed, or never logged in to the forum)'
        return f'could not be checked ({e})'
    if forum_id is None:
        return 'could not be checked (the forum is disabled)'
    return f'forum id {forum_id}'


def _forum_target(client, removal):
    """Describe the forum account to merge into; only reads the forum."""
    try:
        target = client.get_forum_user(removal.target_forum_id)
    except Exception as e:
        return f'forum id {removal.target_forum_id}, could not be checked ({e})'
    if not target:
        return f'forum id {removal.target_forum_id}, could not be checked'
    return f'forum id {removal.target_forum_id} ({target["username"]})'


def preview(client, removal):
    """Return the lines telling what processing a request would remove."""
    lines = [describe(removal)]
    if DBSession.get(User, removal.user_id) is None:
        lines.append(f'  topoguide account {removal.user_id}: does not exist anymore')
    target = DBSession.get(User, removal.target_user_id)
    if target is None:
        lines.append(
            f'  target account {removal.target_user_id}: DOES NOT EXIST, '
            'the request will fail'
        )
    else:
        lines.append(f'  topoguide account merged into {target.id} ({target.name})')
    lines.append(f'  forum account: {_forum_account(client, removal)}')
    if removal.reason == REASON_SPAM:
        lines.append('  forum account deleted with its posts')
        documents = find_purged_documents(removal.user_id)
        lines.append(f'  {len(documents)} document(s) deleted for good:')
        lines.extend(
            f'    {document_id} ({document_type})'
            for document_id, document_type in documents
        )
    else:
        lines.append(f'  forum account merged into {_forum_target(client, removal)}')
    return lines


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Remove the accounts (else the requests are only listed)',
    )
    parser.add_argument(
        '--grace-hours',
        type=int,
        default=DEFAULT_GRACE_HOURS,
        help='Delay between the last validation and the removal',
    )
    parser.add_argument(
        '--id',
        type=int,
        action='append',
        dest='ids',
        help='Only this request (can be repeated)',
    )
    return parser.parse_args(argv)


def main(argv=sys.argv):
    args = parse_args(argv[1:])

    settings_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), '../../../production.ini'
    )
    settings = get_appsettings(settings_file)
    engine = engine_from_config(settings, 'sqlalchemy.')
    DBSession.configure(bind=engine)
    queue_config = get_queue_config(settings)

    logging.basicConfig()
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARN)

    sys.exit(run(args, settings, queue_config))


def run(args, settings, queue_config):
    """List (or process with --execute) the ready requests; return the exit code."""
    client = get_discourse_client(settings)
    if args.execute and not client.enabled:
        print('The forum is disabled (discourse.enabled): nothing can be removed.')
        return 1

    now = datetime.datetime.now(datetime.UTC)
    removals = find_ready_requests(now, args.grace_hours, args.ids)
    for removal_id in sorted(set(args.ids or []) - {r.id for r in removals}):
        print(f'The request #{removal_id} is not ready (or does not exist).')
    if not removals:
        print('No removal to process.')
        return 0

    failed = 0
    for removal in removals:
        removal_id = removal.id
        if not args.execute:
            print('\n'.join(preview(client, removal)))
            continue
        print(describe(removal))
        try:
            if process_removal(removal_id, settings, queue_config, args.grace_hours):
                print(f'SUCCESS: request #{removal_id} done')
        except OperationalError as e:
            DBSession.rollback()
            if getattr(e.orig, 'pgcode', None) != '55P03':  # lock_not_available
                failed += 1
                log.error('Request #%d failed', removal_id, exc_info=True)
            else:
                print(f'The request #{removal_id} is processed by another run.')
        except Exception:
            failed += 1
            DBSession.rollback()
            log.error('Request #%d failed', removal_id, exc_info=True)

    if not args.execute:
        print('Nothing done: use --execute to remove these accounts.')
    return 1 if failed else 0


if __name__ == '__main__':
    main()
