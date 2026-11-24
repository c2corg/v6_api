import argparse
import logging
import os
import sys

from sqlalchemy import engine_from_config
from sqlalchemy.sql.expression import and_, any_, or_
from sqlalchemy.sql.functions import func

from c2corg_api.config import get_appsettings
from c2corg_api.models import DBSession, commit_or_rollback
from c2corg_api.models.area_association import AreaAssociation
from c2corg_api.models.association import AssociationLog
from c2corg_api.models.cache_version import (
    update_cache_version_direct,
    update_cache_version_full,
)
from c2corg_api.models.document_history import HistoryMetaData
from c2corg_api.models.favourite import Favourite, FavouriteFolder, FavouriteLog
from c2corg_api.models.feed import DocumentChange, FilterArea, FollowedUser
from c2corg_api.models.mailinglist import Mailinglist
from c2corg_api.models.sso import SsoExternalId
from c2corg_api.models.token import Token
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import (
    USERPROFILE_TYPE,
    ArchiveUserProfile,
    UserProfile,
)
from c2corg_api.search import get_queue_config
from c2corg_api.search.notify_sync import notify_es_syncer
from c2corg_api.views.document_delete import (
    remove_from_cache,
    remove_whole_document,
    update_deleted_documents_list,
)
from c2corg_api.views.document_merge import _and_in, transfer_associations
from c2corg_api.views.document_trash import forget_user


def usage(argv):
    cmd = os.path.basename(argv[0])
    exit(
        f'usage: {cmd} <source_user_id> <target_user_id>\n'
        f'(example: {cmd} 123456 811780")'
    )


def exit(msg):
    print(msg)
    sys.exit(1)


def main(argv=sys.argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('src_id', help='Source user identifier', type=int)
    parser.add_argument('tgt_id', help='Target user identifier', type=int)
    parser.add_argument(
        '-f', '--force', action='store_true', help='Merge user without confirmation'
    )
    args = parser.parse_args()

    source_user_id = args.src_id
    target_user_id = args.tgt_id

    if source_user_id == target_user_id:
        exit('ERROR: source and target user accounts cannot be the same')

    settings_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), '../../../production.ini'
    )
    settings = get_appsettings(settings_file)

    engine = engine_from_config(settings, 'sqlalchemy.')
    DBSession.configure(bind=engine)

    queue_config = get_queue_config(settings)

    logging.basicConfig()
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARN)

    source_user = DBSession.get(User, source_user_id)
    if not source_user:
        exit(f'ERROR: source user account (id {source_user_id}) does not exist')

    target_user = DBSession.get(User, target_user_id)
    if not target_user:
        exit(f'ERROR: target user account (id {target_user_id}) does not exist')

    if not args.force:
        sys.stdout.write(
            '\n'
            'Are you sure you want to merge the following accounts? [y/N]\n'
            f'source: id {source_user.id}: '
            f'{source_user.name}/{source_user.forum_username}\n'
            f'target: id {target_user.id}: '
            f'{target_user.name}/{target_user.forum_username}\n'
        )
        if input().lower()[:1] != 'y':
            exit('ABORTED: User accounts merging has been aborted')

    print(
        f'Merging user account {source_user_id} to user account {target_user_id}'
        ' in progress.\n'
        'Please wait...'
    )

    with commit_or_rollback(DBSession):
        merge_user_accounts(source_user_id, target_user_id, queue_config)

    print(
        f'SUCCESS: User account {source_user_id} has been merged to user account '
        f'{target_user_id}'
    )


def merge_user_accounts(source_user_id, target_user_id, queue_config):
    print('Removing from cache...')
    remove_from_cache(source_user_id)
    print('Removing geo associations...')
    _remove_geo_associations(source_user_id)
    print('Transfering associations...')
    _transfer_associations(source_user_id, target_user_id)
    print('Transfering favourites and their folders...')
    _transfer_favourites(source_user_id, target_user_id)
    print('Updating feed entries...')
    _update_feed_entries(source_user_id, target_user_id)
    print('Updating contributions versions and histories...')
    _update_history_metadata(source_user_id, target_user_id)
    print('Updating deleted documents...')
    removed, rewritten = forget_user(source_user_id, target_user_id)
    print(f'{removed} removed (only by this user), {rewritten} transferred')
    print('Unregistering from mailing lists...')
    _unregister_from_mailinglists(source_user_id)
    print('Removing profile and user account...')
    _remove_user_account(source_user_id)

    # update the cache version for the source and target user accounts
    print('Updating associated documents cache...')
    update_cache_version_direct(source_user_id)
    update_cache_version_full(target_user_id, USERPROFILE_TYPE)

    # notify ES the source account no longer exists
    print('Notifying Elastic Search...')
    notify_es_syncer(queue_config)

    # TODO reassign posts/topics + remove source account in Discourse


def _remove_geo_associations(user_id):
    DBSession.query(AreaAssociation).filter(
        AreaAssociation.document_id == user_id
    ).delete()


def _transfer_associations(source_user_id, target_user_id):
    transfer_associations(source_user_id, target_user_id)
    # Also reassign the association author in association logs
    # to the target user:
    DBSession.query(AssociationLog).filter(
        AssociationLog.user_id == source_user_id
    ).update({AssociationLog.user_id: target_user_id})


def _transfer_favourites(source_user_id, target_user_id):
    _transfer_favourite_folders(source_user_id, target_user_id)

    target_document_ids_result = (
        DBSession.query(Favourite.document_id)
        .filter(Favourite.user_id == target_user_id)
        .all()
    )
    target_document_ids = [document_id for (document_id,) in target_document_ids_result]
    # move the current favourites, with their folder and date (only if the
    # target user does not already have the same document in favourites)
    transfered_documents_result = DBSession.execute(
        Favourite.__table__.update()
        .where(
            _and_in(
                Favourite.user_id == source_user_id,
                Favourite.document_id,
                target_document_ids,
            )
        )
        .values(user_id=target_user_id)
        .returning(Favourite.document_id, Favourite.document_type)
    )

    # remove remaining favourites
    DBSession.execute(
        Favourite.__table__.delete().where(Favourite.user_id == source_user_id)
    )

    # remove all existing logs
    DBSession.execute(
        FavouriteLog.__table__.delete().where(FavouriteLog.user_id == source_user_id)
    )

    # create new ones for the transfered favourites
    transfered_documents = [
        {
            'document_id': document_id,
            'user_id': target_user_id,
            'document_type': document_type,
            'is_creation': True,
            'written_at': func.now(),
        }
        for (document_id, document_type) in transfered_documents_result
    ]
    if len(transfered_documents):
        DBSession.execute(FavouriteLog.__table__.insert().values(transfered_documents))


def _transfer_favourite_folders(source_user_id, target_user_id):
    # A folder named as one of the target user's is merged into it, the
    # others are moved after the folders of the target user.
    target_folders = dict(
        DBSession.query(FavouriteFolder.name, FavouriteFolder.id).filter(
            FavouriteFolder.user_id == target_user_id
        )
    )
    last_position = (
        DBSession.query(func.max(FavouriteFolder.position))
        .filter(FavouriteFolder.user_id == target_user_id)
        .scalar()
    )
    position = -1 if last_position is None else last_position
    source_folders = (
        DBSession.query(FavouriteFolder)
        .filter(FavouriteFolder.user_id == source_user_id)
        .order_by(FavouriteFolder.position, FavouriteFolder.id)
        .all()
    )
    for folder in source_folders:
        same_name_id = target_folders.get(folder.name)
        if same_name_id is not None:
            DBSession.query(Favourite).filter(Favourite.folder_id == folder.id).update(
                {Favourite.folder_id: same_name_id}, synchronize_session=False
            )
            DBSession.delete(folder)
        else:
            position += 1
            folder.user_id = target_user_id
            folder.position = position
    DBSession.flush()


def _update_feed_entries(source_user_id, target_user_id):
    # Transfer feed entries to the target user only if no similar entry
    # already exists in the target user feed items.
    shared_doc_ids = (
        DBSession.query(DocumentChange.document_id)
        .filter(DocumentChange.user_id == target_user_id)
        .intersect(
            DBSession.query(DocumentChange.document_id).filter(
                DocumentChange.user_id == source_user_id
            )
        )
        .scalar_subquery()
    )
    DBSession.execute(
        DocumentChange.__table__.update()
        .where(
            and_(
                DocumentChange.user_id == source_user_id,
                ~DocumentChange.document_id.in_(shared_doc_ids),
            )
        )
        .values({DocumentChange.user_id: target_user_id})
    )
    # Remove remaining feed items since they already exist for the target user
    DBSession.query(DocumentChange).filter(
        DocumentChange.user_id == source_user_id
    ).delete()

    # If target user_id is already in the list of users associated
    # to feed items (user_ids), simply remove source user_id from the list:
    DBSession.execute(
        DocumentChange.__table__.update()
        .where(
            and_(
                any_(DocumentChange.user_ids) == source_user_id,
                any_(DocumentChange.user_ids) == target_user_id,
            )
        )
        .values(
            {
                DocumentChange.user_ids: func.array_remove(
                    DocumentChange.user_ids, source_user_id
                )
            }
        )
    )
    # Else replace source user_id by target user_id in user_ids
    DBSession.execute(
        DocumentChange.__table__.update()
        .where(any_(DocumentChange.user_ids) == source_user_id)
        .values(
            {
                DocumentChange.user_ids: func.array_replace(
                    DocumentChange.user_ids, source_user_id, target_user_id
                )
            }
        )
    )

    # Remove subscriptions to/of the source user
    DBSession.query(FollowedUser).filter(
        or_(
            FollowedUser.followed_user_id == source_user_id,
            FollowedUser.follower_user_id == source_user_id,
        )
    ).delete()

    # Remove feed filter prefs
    DBSession.query(FilterArea).filter(FilterArea.user_id == source_user_id).delete()


def _update_history_metadata(source_user_id, target_user_id):
    DBSession.query(HistoryMetaData).filter(
        HistoryMetaData.user_id == source_user_id
    ).update({HistoryMetaData.user_id: target_user_id})


def _unregister_from_mailinglists(user_id):
    email = DBSession.query(User.email).filter(User.id == user_id).scalar_subquery()
    DBSession.execute(Mailinglist.__table__.delete().where(Mailinglist.email == email))


def _remove_user_account(user_id):
    DBSession.query(SsoExternalId).filter(SsoExternalId.user_id == user_id).delete()
    DBSession.query(Token).filter(Token.userid == user_id).delete()
    DBSession.query(User).filter(User.id == user_id).delete()
    # Delete profile document and its archives
    remove_whole_document(user_id, UserProfile, None, ArchiveUserProfile, None)
    update_deleted_documents_list(user_id, USERPROFILE_TYPE)


if __name__ == '__main__':
    main()
