"""Remove the accounts of the validated removal requests.

A request (see views/user_removal.py) is processed once it is validated by a
moderator of the topoguide and by one of the forum, its date is past, and a
delay has elapsed since its last validation (to leave time to cancel a
validation made by mistake).

The script only lists the requests to process, unless `--execute` is given:

    python -m c2corg_api.scripts.users.process_removals
    python -m c2corg_api.scripts.users.process_removals --execute

For each request:
- spam: the documents the user alone contributed to (outings, reports,
  articles and images) are deleted, as well as the account of the forum with its
  posts;
- else: the account of the forum is merged into the target one;
- then the account of the topoguide is merged into the target one, as with
  scripts/users/merge.py.
"""

import argparse
import datetime
import logging
import os
import sys
from types import SimpleNamespace

from sqlalchemy import engine_from_config
from sqlalchemy.sql.expression import and_, exists

from c2corg_api.config import get_appsettings
from c2corg_api.models import DBSession, commit_or_rollback
from c2corg_api.models.account_removal import REASON_SPAM, AccountRemovalRequest
from c2corg_api.models.article import ARTICLE_TYPE
from c2corg_api.models.document import Document
from c2corg_api.models.document_history import DocumentVersion, HistoryMetaData
from c2corg_api.models.image import IMAGE_TYPE
from c2corg_api.models.outing import OUTING_TYPE
from c2corg_api.models.user import User
from c2corg_api.models.xreport import XREPORT_TYPE
from c2corg_api.scripts.users.merge import merge_user_accounts
from c2corg_api.search import get_queue_config
from c2corg_api.security.discourse_client import get_discourse_client
from c2corg_api.views.document_delete import _delete

log = logging.getLogger(__name__)

# the documents that may be deleted with a spammer: the types a user creates
# alone (a waypoint or a route is also used by the other contributors)
PURGED_TYPES = [OUTING_TYPE, XREPORT_TYPE, ARTICLE_TYPE, IMAGE_TYPE]

# delay between the last validation and the removal
DEFAULT_GRACE_HOURS = 24


def find_ready_requests(now, grace_hours=DEFAULT_GRACE_HOURS):
    """Return the requests validated by both sides, which can be processed."""
    today = now.date()
    limit = now - datetime.timedelta(hours=grace_hours)
    requests = (
        DBSession.query(AccountRemovalRequest)
        .filter(
            AccountRemovalRequest.done_at.is_(None),
            AccountRemovalRequest.topoguide_validated_by.is_not(None),
            AccountRemovalRequest.forum_validated_by.is_not(None),
            AccountRemovalRequest.executable_after <= today,
            AccountRemovalRequest.topoguide_validated_at <= limit,
            AccountRemovalRequest.forum_validated_at <= limit,
        )
        .order_by(AccountRemovalRequest.id)
        .all()
    )
    return requests


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
    """Delete the documents only this user contributed to."""
    # `_delete` is the deletion of the views: it only reads the registry
    request = SimpleNamespace(
        registry=SimpleNamespace(settings=settings, queue_config=queue_config)
    )
    documents = find_purged_documents(user_id)
    for document_id, document_type in documents:
        print(f'Deleting the document {document_id} ({document_type})...')
        _delete(request, document_id, document_type)
    return len(documents)


def _is_not_found(error):
    response = getattr(error, 'response', None)
    return response is not None and response.status_code == 404


def _remove_forum_account(client, removal):
    """Merge (or delete for a spammer) the account of the forum."""
    try:
        if removal.reason == REASON_SPAM:
            print('Deleting the forum account and its posts...')
            client.delete_user(removal.user_id, delete_posts=True)
        else:
            print('Merging the forum account...')
            client.merge_user(removal.user_id, removal.target_forum_id)
    except Exception as e:
        # already removed by a previous run, which failed afterwards
        if not _is_not_found(e):
            raise
        print('The forum account does not exist anymore.')


def process_removal(removal_id, settings, queue_config):
    """Remove the account of a request."""
    removal = DBSession.get(AccountRemovalRequest, removal_id)
    user_id = removal.user_id
    if DBSession.get(User, user_id) is None:
        # merged by hand since the request
        print(f'The account {user_id} does not exist anymore.')
    elif DBSession.get(User, removal.target_user_id) is None:
        raise ValueError(f'The target account {removal.target_user_id} does not exist')

    # the forum first: it can be done again if the next step fails
    client = get_discourse_client(settings)
    _remove_forum_account(client, removal)

    if DBSession.get(User, user_id) is not None:
        with commit_or_rollback(DBSession):
            if removal.reason == REASON_SPAM:
                purge_contributions(user_id, settings, queue_config)
            merge_user_accounts(user_id, removal.target_user_id, queue_config)
            removal.done_at = datetime.datetime.now(datetime.UTC)
    else:
        with commit_or_rollback(DBSession):
            removal.done_at = datetime.datetime.now(datetime.UTC)


def describe(removal):
    return (
        f'#{removal.id}: {removal.reason}, account {removal.user_id} '
        f'({removal.user_name}/{removal.user_forum_username}) -> '
        f'{removal.target_user_id} (forum {removal.target_forum_id})'
    )


def main(argv=sys.argv):
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
    args = parser.parse_args(argv[1:])

    settings_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), '../../../production.ini'
    )
    settings = get_appsettings(settings_file)
    engine = engine_from_config(settings, 'sqlalchemy.')
    DBSession.configure(bind=engine)
    queue_config = get_queue_config(settings)

    logging.basicConfig()
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARN)

    now = datetime.datetime.now(datetime.UTC)
    removals = find_ready_requests(now, args.grace_hours)
    if not removals:
        print('No removal to process.')
        return

    failed = 0
    for removal in removals:
        removal_id = removal.id
        print(describe(removal))
        if not args.execute:
            continue
        try:
            process_removal(removal_id, settings, queue_config)
            print(f'SUCCESS: request #{removal_id} done')
        except Exception:
            failed += 1
            DBSession.rollback()
            log.error('Request #%d failed', removal_id, exc_info=True)

    if not args.execute:
        print('Nothing done: use --execute to remove these accounts.')
    if failed:
        sys.exit(1)


if __name__ == '__main__':
    main()
