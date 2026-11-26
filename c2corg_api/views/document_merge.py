from sqlalchemy import not_
from sqlalchemy.sql.expression import and_, or_
from sqlalchemy.sql.functions import func

from c2corg_api.models import DBSession
from c2corg_api.models.association import Association, AssociationLog
from c2corg_api.models.cache_version import (
    update_cache_version_direct,
    update_cache_version_full,
)
from c2corg_api.models.document import Document, UpdateType
from c2corg_api.models.favourite import Favourite, FavouriteLog
from c2corg_api.models.feed import DocumentChange
from c2corg_api.models.image import IMAGE_TYPE
from c2corg_api.models.route import Route
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.models.waypoint import WAYPOINT_TYPE, Waypoint
from c2corg_api.schemas.base import Schema, body_validator
from c2corg_api.schemas.types import Int
from c2corg_api.search.notify_sync import notify_es_syncer
from c2corg_api.views.document import update_version
from c2corg_api.views.document_unmerge import keep_merge
from c2corg_api.views.image import delete_all_files_for_image
from c2corg_api.views.resource import write
from c2corg_api.views.waypoint import update_linked_route_titles


class MergeSchema(Schema):
    source_document_id: Int
    target_document_id: Int


def validate_documents(request, **kwargs):
    """Check that.

    - the documents exists.
    - the documents are of the same type.
    - the type is not USERPROFILE_TYPE.
    - the documents are not redirected yet.
    """
    if (
        'source_document_id' not in request.validated
        or 'target_document_id' not in request.validated
    ):
        return

    source_document_id = request.validated['source_document_id']
    target_document_id = request.validated['target_document_id']

    if source_document_id == target_document_id:
        request.errors.add(
            'body', 'target_document_id', 'Cannot merge document with itself'
        )
        return

    source_info = (
        DBSession.query(Document.redirects_to, Document.type)
        .filter(Document.document_id == source_document_id)
        .first()
    )

    target_info = (
        DBSession.query(Document.redirects_to, Document.type)
        .filter(Document.document_id == target_document_id)
        .first()
    )

    # do the documents exist?
    if not source_info or not target_info:
        if not source_info:
            request.errors.add(
                'body',
                'source_document_id',
                f'document {source_document_id} does not exist',
            )
        if not target_info:
            request.errors.add(
                'body',
                'target_document_id',
                f'document {target_document_id} does not exist',
            )
        return

    (source_redirects_to, source_type) = source_info
    (target_redirects_to, target_type) = target_info

    # are the documents not already merged?
    if source_redirects_to or target_redirects_to:
        if source_redirects_to:
            request.errors.add(
                'body',
                'source_document_id',
                f'document {source_document_id} is already redirected',
            )
        if target_redirects_to:
            request.errors.add(
                'body',
                'target_document_id',
                f'document {target_document_id} is also redirected',
            )
        return

    # do they have the same type?
    if source_type != target_type:
        request.errors.add('body', 'types', 'documents must have the same type')

    if source_type == USERPROFILE_TYPE:
        request.errors.add('body', 'types', 'merging user accounts is not supported')


@write(
    validators=[body_validator(MergeSchema), validate_documents],
    permission='moderator',
    json=True,
)
def merge_documents(request):
    """Merge a document into another document.

    - Associations and favourites of the source document are transferred to
      the target document.
    - The association log entries are rewritten to the target document.
    - The time of the log entries is updated, so that the ES syncer will
      pick up the new associations of the target document.
    - The attribute `redirects_to` of the source document is set, and of the
      documents merged into the source before.
    - A new version is created for the source document. This makes sure
      that the ES syncer removes the document from ES index.
    - Update the cache version of the source document.
    - Update the cache version of the target document and its associations.
    - Removes the feed entries of the source document.


    Request:
        `POST` `/documents/merge`

    Request body:
        {
            'source_document_id': @document_id@,
            'target_document_id': @document_id@
        }
    """
    source_document_id = request.validated['source_document_id']
    target_document_id = request.validated['target_document_id']
    source_doc = DBSession.get(Document, source_document_id)

    # kept before anything changes, to undo the merge
    keep_merge(request, source_document_id, target_document_id, source_doc.type)

    # transfer associations from source to target
    transfer_associations(source_document_id, target_document_id)

    # transfer favourites from source to target
    transfer_favourites(source_document_id, target_document_id)

    # if waypoint, update main waypoint of routes
    if source_doc.type == WAYPOINT_TYPE:
        _transfer_main_waypoint(source_document_id, target_document_id)

    # the documents merged into the source before now redirect to the target:
    # one level of redirection only (a merged image shows the files of its
    # target, those of the source are deleted below)
    redirected_ids = _redirect_merged_documents(source_document_id, target_document_id)

    # set redirection and create a new version
    source_doc.redirects_to = target_document_id
    update_version(
        source_doc,
        request.authenticated_userid,
        f'merged with {target_document_id}',
        [UpdateType.FIGURES],
        [],
    )

    # update the cache version for the source and target document
    update_cache_version_direct(source_document_id)
    for document_id in redirected_ids:
        update_cache_version_direct(document_id)
    update_cache_version_full(target_document_id, source_doc.type)

    _remove_feed_entry(source_document_id)

    if source_doc.type == IMAGE_TYPE:
        delete_all_files_for_image(source_document_id, request)

    notify_es_syncer(request.registry.queue_config)

    return {}


def _redirect_merged_documents(source_document_id, target_document_id):
    """Point the documents redirecting to the source to the target."""
    redirected_ids = (
        DBSession.query(Document.document_id)
        .filter(Document.redirects_to == source_document_id)
        .all()
    )
    redirected_ids = [document_id for (document_id,) in redirected_ids]
    if redirected_ids:
        DBSession.query(Document).filter(
            Document.document_id.in_(redirected_ids)
        ).update({Document.redirects_to: target_document_id}, synchronize_session=False)
    return redirected_ids


def transfer_associations(source_document_id, target_document_id):
    # get the document ids the target is already associated with
    target_child_ids_result = (
        DBSession.query(Association.child_document_id)
        .filter(Association.parent_document_id == target_document_id)
        .all()
    )
    target_child_ids = [child_id for (child_id,) in target_child_ids_result]
    target_parent_ids_result = (
        DBSession.query(Association.parent_document_id)
        .filter(Association.child_document_id == target_document_id)
        .all()
    )
    target_parent_ids = [parent_id for (parent_id,) in target_parent_ids_result]

    # move the current associations (only if the target document does not
    # already have an association with the same document)
    DBSession.execute(
        Association.__table__.update()
        .where(
            _and_in(
                Association.parent_document_id == source_document_id,
                Association.child_document_id,
                target_child_ids,
            )
        )
        .values(parent_document_id=target_document_id)
    )
    DBSession.execute(
        Association.__table__.update()
        .where(
            _and_in(
                Association.child_document_id == source_document_id,
                Association.parent_document_id,
                target_parent_ids,
            )
        )
        .values(child_document_id=target_document_id)
    )

    # remove remaining associations
    DBSession.execute(
        Association.__table__.delete().where(
            or_(
                Association.child_document_id == source_document_id,
                Association.parent_document_id == source_document_id,
            )
        )
    )

    # transfer the association log entries
    DBSession.execute(
        AssociationLog.__table__.update()
        .where(
            _and_in(
                AssociationLog.parent_document_id == source_document_id,
                AssociationLog.child_document_id,
                target_child_ids,
            )
        )
        .values(parent_document_id=target_document_id, written_at=func.now())
    )
    DBSession.execute(
        AssociationLog.__table__.update()
        .where(
            _and_in(
                AssociationLog.child_document_id == source_document_id,
                AssociationLog.parent_document_id,
                target_parent_ids,
            )
        )
        .values(child_document_id=target_document_id, written_at=func.now())
    )

    DBSession.execute(
        AssociationLog.__table__.delete().where(
            or_(
                AssociationLog.child_document_id == source_document_id,
                AssociationLog.parent_document_id == source_document_id,
            )
        )
    )


def transfer_favourites(source_document_id, target_document_id):
    # get the ids of users that already have the target document in favourites
    target_user_ids_result = (
        DBSession.query(Favourite.user_id)
        .filter(Favourite.document_id == target_document_id)
        .all()
    )
    target_user_ids = [user_id for (user_id,) in target_user_ids_result]

    # move the current favourites, with their folder and date (only if the
    # target document is not already a favourite of the same user)
    DBSession.execute(
        Favourite.__table__.update()
        .where(
            _and_in(
                Favourite.document_id == source_document_id,
                Favourite.user_id,
                target_user_ids,
            )
        )
        .values(document_id=target_document_id)
    )

    # remove remaining favourites
    DBSession.execute(
        Favourite.__table__.delete().where(Favourite.document_id == source_document_id)
    )

    # transfer the favourite log entries
    DBSession.execute(
        FavouriteLog.__table__.update()
        .where(
            _and_in(
                FavouriteLog.document_id == source_document_id,
                FavouriteLog.user_id,
                target_user_ids,
            )
        )
        .values(document_id=target_document_id, written_at=func.now())
    )

    DBSession.execute(
        FavouriteLog.__table__.delete().where(
            FavouriteLog.document_id == source_document_id
        )
    )


def _and_in(condition1, field2, in_ids):
    if not in_ids:
        return condition1
    else:
        return and_(condition1, not_(field2.in_(in_ids)))


def _transfer_main_waypoint(source_document_id, target_document_id):
    target_waypoint = DBSession.get(Waypoint, target_document_id)

    DBSession.execute(
        Route.__table__.update()
        .where(Route.main_waypoint_id == source_document_id)
        .values(main_waypoint_id=target_document_id)
    )
    update_linked_route_titles(target_waypoint, [UpdateType.LANG], None)


def _remove_feed_entry(source_document_id):
    DBSession.query(DocumentChange).filter(
        DocumentChange.document_id == source_document_id
    ).delete()
