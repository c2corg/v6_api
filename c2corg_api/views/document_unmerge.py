"""Undo a merge: what a merge moves and removes is kept a while to be undone."""

# A merge (views.document_merge) moves the associations, favourites and their
# logs of the source document to the target, removes those the target already
# had, points the routes of a source waypoint and the documents merged into the
# source before to the target, removes the feed entry of the source and the
# files of a source image. Just before, `keep_merge` keeps in a
# `MergedDocument`:
# - the keys of the rows it moves (associations, favourites) and the ids of the
#   log rows it moves,
# - the rows it removes, as the soft delete keeps them (document_trash.Snapshot),
# - the routes and the documents it points to the target, the image files.
#
# `unmerge` moves back what is still where the merge put it, unless it was
# written again since the merge (an association removed and added again stays
# with the target), and inserts the removed rows again.

from datetime import UTC, datetime

from sqlalchemy import and_, exists, or_
from sqlalchemy.sql.expression import select
from sqlalchemy.sql.functions import func

from c2corg_api.httpexceptions import HTTPBadRequest, HTTPNotFound
from c2corg_api.models import DBSession
from c2corg_api.models.association import Association, AssociationLog
from c2corg_api.models.cache_version import (
    update_cache_version_direct,
    update_cache_version_full,
)
from c2corg_api.models.common.attributes import default_langs
from c2corg_api.models.deleted_document import RETENTION
from c2corg_api.models.document import Document, DocumentLocale, UpdateType
from c2corg_api.models.favourite import Favourite, FavouriteLog
from c2corg_api.models.feed import DocumentChange
from c2corg_api.models.image import IMAGE_TYPE, ArchiveImage
from c2corg_api.models.merged_document import MergedDocument
from c2corg_api.models.route import Route
from c2corg_api.models.waypoint import WAYPOINT_TYPE, Waypoint
from c2corg_api.search.notify_sync import notify_es_syncer
from c2corg_api.views.document_trash import Snapshot, _insert, _user, _users
from c2corg_api.views.resource import write
from c2corg_api.views.validation import validate_id

# the version of the snapshot format
FORMAT = 1

# the tables whose removed rows a merge keeps, in the order to insert them
_REMOVED_TABLES = (
    Association.__table__,
    AssociationLog.__table__,
    Favourite.__table__,
    FavouriteLog.__table__,
    DocumentChange.__table__,
)


def keep_merge(request, source_document_id, target_document_id, document_type):
    """Keep what a merge moves and removes, to undo it."""
    # called by views.document_merge before the merge changes anything
    source = source_document_id
    target = target_document_id
    removed = Snapshot()

    target_children = select(Association.child_document_id).where(
        Association.parent_document_id == target
    )
    target_parents = select(Association.parent_document_id).where(
        Association.child_document_id == target
    )

    def removed_link(t):
        # the rows linking the source with a document the target is also
        # linked with are removed, the others moved (as views.document_merge);
        # `t` is the table of the associations or of their logs, or an alias
        return or_(
            and_(
                t.c.parent_document_id == source,
                t.c.child_document_id.in_(target_children),
            ),
            and_(
                t.c.child_document_id == source,
                t.c.parent_document_id.in_(target_parents),
            ),
        )

    def of_source(t):
        return or_(t.c.parent_document_id == source, t.c.child_document_id == source)

    associations = Association.__table__
    moved_associations = DBSession.execute(
        select(
            associations.c.parent_document_id, associations.c.child_document_id
        ).where(of_source(associations), ~removed_link(associations))
    ).all()
    removed.capture(Association, removed_link)

    logs = AssociationLog.__table__
    moved_logs = DBSession.execute(
        select(logs.c.id, logs.c.parent_document_id).where(
            of_source(logs), ~removed_link(logs)
        )
    ).all()
    removed.capture(AssociationLog, removed_link)

    target_users = select(Favourite.user_id).where(Favourite.document_id == target)
    moved_favourites = (
        DBSession.execute(
            select(Favourite.user_id).where(
                Favourite.document_id == source, ~Favourite.user_id.in_(target_users)
            )
        )
        .scalars()
        .all()
    )
    removed.capture(
        Favourite,
        lambda r: and_(r.c.document_id == source, r.c.user_id.in_(target_users)),
    )
    moved_favourite_logs = (
        DBSession.execute(
            select(FavouriteLog.id).where(
                FavouriteLog.document_id == source,
                ~FavouriteLog.user_id.in_(target_users),
            )
        )
        .scalars()
        .all()
    )
    removed.capture(
        FavouriteLog,
        lambda r: and_(r.c.document_id == source, r.c.user_id.in_(target_users)),
    )

    removed.capture(DocumentChange, lambda r: r.c.document_id == source)

    routes = []
    if document_type == WAYPOINT_TYPE:
        routes = (
            DBSession.execute(
                select(Route.document_id).where(Route.main_waypoint_id == source)
            )
            .scalars()
            .all()
        )
    redirected = (
        DBSession.execute(
            select(Document.document_id).where(Document.redirects_to == source)
        )
        .scalars()
        .all()
    )
    filenames = []
    if document_type == IMAGE_TYPE:
        filenames = (
            DBSession.execute(
                select(ArchiveImage.filename)
                .where(ArchiveImage.document_id == source)
                .distinct()
            )
            .scalars()
            .all()
        )

    DBSession.add(
        MergedDocument(
            source_document_id=source,
            target_document_id=target,
            document_type=document_type,
            title=_title(source),
            merged_by=request.authenticated_userid,
            snapshot={
                'format': FORMAT,
                # [parent id, child id] before the merge
                'associations': [list(key) for key in moved_associations],
                # [log id, true when the source was the parent]
                'association_logs': [
                    [log_id, parent_id == source] for log_id, parent_id in moved_logs
                ],
                'favourites': list(moved_favourites),
                'favourite_logs': list(moved_favourite_logs),
                'removed': removed.tables,
                'main_waypoint_of': list(routes),
                'redirected': list(redirected),
                'filenames': sorted(f for f in filenames if f),
            },
        )
    )


def _title(document_id):
    locales = dict(
        DBSession.execute(
            select(DocumentLocale.lang, DocumentLocale.title).where(
                DocumentLocale.document_id == document_id
            )
        ).all()
    )
    return next((locales[lang] for lang in default_langs if lang in locales), None)


def expired_before():
    """Return the time before which a merge can no longer be undone."""
    return datetime.now(UTC) - RETENTION


def get_entry(entry_id):
    entry = DBSession.get(MergedDocument, entry_id)
    if entry is None:
        raise HTTPNotFound(f'Unknown merge {entry_id}')
    return entry


def _check_unmergeable(entry):
    if entry.unmerged_at is not None:
        raise HTTPBadRequest('This merge was already undone')
    if entry.merged_at < expired_before():
        raise HTTPBadRequest('This merge was done too long ago')
    if entry.snapshot.get('format') != FORMAT:
        raise HTTPBadRequest('Unknown format of the merge')
    source = DBSession.get(Document, entry.source_document_id)
    target = DBSession.get(Document, entry.target_document_id)
    if source is None or target is None:
        raise HTTPBadRequest('A document of the merge was deleted')
    if target.redirects_to is not None:
        # the source redirects to the new target too
        raise HTTPBadRequest(
            'The target was merged since into another document: undo that first'
        )
    if source.redirects_to != target.document_id:
        raise HTTPBadRequest('The source no longer redirects to the target')
    return source, target


def unmerge(request, entry):
    """Undo a merge, the changes made to the target since kept."""
    source, target = _check_unmergeable(entry)
    source_id = source.document_id
    target_id = target.document_id
    merged_at = entry.merged_at
    snapshot = entry.snapshot
    user_id = request.authenticated_userid
    skipped = {}

    def skip(name):
        skipped[name] = skipped.get(name, 0) + 1

    def at_target(document_id):
        return target_id if document_id == source_id else document_id

    for parent_id, child_id in snapshot['associations']:
        moved = (at_target(parent_id), at_target(child_id))
        if _written_since(AssociationLog, merged_at, *moved):
            skip('associations')
            continue
        count = (
            DBSession.query(Association)
            .filter(
                Association.parent_document_id == moved[0],
                Association.child_document_id == moved[1],
            )
            .update(
                {
                    Association.parent_document_id: parent_id,
                    Association.child_document_id: child_id,
                },
                synchronize_session=False,
            )
        )
        if not count:
            skip('associations')

    # the log rows moved back are dated now, as the merge did: the search
    # index sync sees the associations changed
    for log_id, source_was_parent in snapshot['association_logs']:
        side = (
            AssociationLog.parent_document_id
            if source_was_parent
            else AssociationLog.child_document_id
        )
        DBSession.query(AssociationLog).filter(
            AssociationLog.id == log_id, side == target_id
        ).update(
            {side: source_id, AssociationLog.written_at: func.now()},
            synchronize_session=False,
        )

    for favourite_user_id in snapshot['favourites']:
        if _written_since(FavouriteLog, merged_at, favourite_user_id, target_id):
            skip('favourites')
            continue
        count = (
            DBSession.query(Favourite)
            .filter(
                Favourite.user_id == favourite_user_id,
                Favourite.document_id == target_id,
            )
            .update({Favourite.document_id: source_id}, synchronize_session=False)
        )
        if not count:
            skip('favourites')
    if snapshot['favourite_logs']:
        DBSession.query(FavouriteLog).filter(
            FavouriteLog.id.in_(snapshot['favourite_logs']),
            FavouriteLog.document_id == target_id,
        ).update(
            {FavouriteLog.document_id: source_id, FavouriteLog.written_at: func.now()},
            synchronize_session=False,
        )

    removed = snapshot['removed']
    for table in _REMOVED_TABLES:
        rows = removed.get(table.fullname)
        if not rows:
            continue
        inserted = _insert(table, rows)
        if inserted < len(rows):
            skip_count = len(rows) - inserted
            skipped[table.name] = skipped.get(table.name, 0) + skip_count
    association_log_ids = [
        row['id'] for row in removed.get(AssociationLog.__table__.fullname, [])
    ]
    if association_log_ids:
        DBSession.query(AssociationLog).filter(
            AssociationLog.id.in_(association_log_ids)
        ).update({AssociationLog.written_at: func.now()}, synchronize_session=False)

    if snapshot['main_waypoint_of']:
        count = (
            DBSession.query(Route)
            .filter(
                Route.document_id.in_(snapshot['main_waypoint_of']),
                Route.main_waypoint_id == target_id,
            )
            .update({Route.main_waypoint_id: source_id}, synchronize_session=False)
        )
        if count < len(snapshot['main_waypoint_of']):
            skipped['main_waypoint_of'] = len(snapshot['main_waypoint_of']) - count

    if snapshot['redirected']:
        DBSession.query(Document).filter(
            Document.document_id.in_(snapshot['redirected']),
            Document.redirects_to == target_id,
        ).update({Document.redirects_to: source_id}, synchronize_session=False)

    DBSession.expire_all()
    source = DBSession.get(Document, source_id)
    source.redirects_to = None
    # a new version: the search index sync indexes the source again
    from c2corg_api.views.document import update_version

    update_version(
        source, user_id, f'unmerged from {target_id}', [UpdateType.FIGURES], []
    )

    if entry.document_type == WAYPOINT_TYPE and snapshot['main_waypoint_of']:
        from c2corg_api.views.waypoint import update_linked_route_titles

        update_linked_route_titles(
            DBSession.get(Waypoint, source_id), [UpdateType.LANG], None
        )

    update_cache_version_full(source_id, entry.document_type)
    update_cache_version_full(target_id, entry.document_type)
    for document_id in snapshot['redirected']:
        update_cache_version_direct(document_id)

    missing_files = []
    if snapshot['filenames']:
        from c2corg_api.views.image import restore_files_of_images

        missing_files = restore_files_of_images(snapshot['filenames'], request)

    entry.unmerged_at = datetime.now(UTC)
    entry.unmerged_by = user_id

    notify_es_syncer(request.registry.queue_config)

    return {
        'source_document_id': source_id,
        'target_document_id': target_id,
        'skipped': skipped,
        'missing_files': missing_files,
    }


def _written_since(log_model, since, first_id, second_id):
    """Whether a log row of the moved row was written after the merge."""
    # an association or favourite removed or added again since the merge
    # belongs to the target now
    if log_model is AssociationLog:
        key = and_(
            AssociationLog.parent_document_id == first_id,
            AssociationLog.child_document_id == second_id,
        )
    else:
        key = and_(
            FavouriteLog.user_id == first_id, FavouriteLog.document_id == second_id
        )
    return DBSession.query(exists().where(key, log_model.written_at > since)).scalar()


def list_entries(offset, limit):
    """Return the merges that can be undone, the last first."""
    query = DBSession.query(MergedDocument).filter(
        MergedDocument.unmerged_at.is_(None),
        MergedDocument.merged_at >= expired_before(),
    )
    total = query.count()
    entries = (
        query.order_by(MergedDocument.merged_at.desc(), MergedDocument.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    users = _users(entry.merged_by for entry in entries)
    return {
        'total': total,
        'merges': [
            {
                'id': entry.id,
                'source_document_id': entry.source_document_id,
                'target_document_id': entry.target_document_id,
                'type': entry.document_type,
                'title': entry.title,
                'merged_at': entry.merged_at.isoformat(),
                'merged_by': _user(users, entry.merged_by),
                'counts': _counts(entry.snapshot),
            }
            for entry in entries
        ],
    }


def _counts(snapshot):
    removed = snapshot['removed']
    return {
        'associations_moved': len(snapshot['associations']),
        'associations_removed': len(removed.get(Association.__table__.fullname, [])),
        'favourites_moved': len(snapshot['favourites']),
        'favourites_removed': len(removed.get(Favourite.__table__.fullname, [])),
        'routes': len(snapshot['main_waypoint_of']),
        'redirected': len(snapshot['redirected']),
        'files': len(snapshot['filenames']),
    }


def purge_expired(session):
    """Remove the merges kept longer than the retention; return how many."""
    # the undone ones too: kept until then to tell who undid what
    return (
        session.query(MergedDocument)
        .filter(MergedDocument.merged_at < expired_before())
        .delete(synchronize_session=False)
    )


# the views (routes in web.document_actions), for the moderators

LIMIT_DEFAULT = 30
LIMIT_MAX = 100


def read_merged_documents(request):
    """List the merges that can be undone.

    Request:
        `GET` `/documents/merged?offset=0&limit=30`
    """
    validated = request.validated
    return list_entries(
        validated.get('offset') or 0,
        min(validated.get('limit') or LIMIT_DEFAULT, LIMIT_MAX),
    )


@write(validators=[validate_id], permission='moderator')
def unmerge_document(request):
    """Undo a merge.

    Request:
        `POST` `/documents/merged/{id}/unmerge`

    Response: what could not be moved back (changed since the merge) or
    inserted again, and the image files without a version left in the bucket:

        {'source_document_id': 1, 'target_document_id': 2,
         'skipped': {'associations': 1}, 'missing_files': []}
    """
    return unmerge(request, get_entry(request.validated['id']))
