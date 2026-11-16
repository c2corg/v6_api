"""Soft delete: the rows a deletion removes are kept a while to be restored."""

# A deletion keeps the rows it removes in a `DeletedDocument` (its snapshot),
# taken just before the removal (see views.document_delete). The tables of the
# documents stay as they were: no query has to filter deleted documents out.
# A moderator lists the deleted documents and restores one: its rows are
# inserted again. The purge job removes the snapshots after `RETENTION`.
#
# The rows are kept as JSON, the values in the text form of PostgreSQL for the
# arrays and the geometries: `jsonb_populate_recordset` turns them back into
# the types of the columns, also with PostgreSQL 9.6 (JSON arrays are only
# read as arrays from PostgreSQL 10).

import json
from datetime import UTC, datetime
from itertools import batched

from geoalchemy2 import Geometry
from sqlalchemy import ARRAY, Integer, Text, and_, case, cast, exists, or_, tuple_
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.sql.expression import literal, literal_column, select
from sqlalchemy.sql.functions import func

from c2corg_api.httpexceptions import (
    HTTPBadRequest,
    HTTPInternalServerError,
    HTTPNotFound,
)
from c2corg_api.models import Base, DBSession
from c2corg_api.models.area import Area
from c2corg_api.models.area_association import AreaAssociation
from c2corg_api.models.association import Association, AssociationLog
from c2corg_api.models.cache_version import update_cache_version_full
from c2corg_api.models.common.attributes import default_langs
from c2corg_api.models.deleted_document import RETENTION, DeletedDocument
from c2corg_api.models.document import (
    ArchiveDocument,
    ArchiveDocumentGeometry,
    ArchiveDocumentLocale,
    Document,
    DocumentGeometry,
    DocumentLocale,
)
from c2corg_api.models.document_history import DocumentVersion, HistoryMetaData
from c2corg_api.models.document_tag import DocumentTag, DocumentTagLog
from c2corg_api.models.document_topic import DocumentTopic
from c2corg_api.models.es_sync import ESDeletedDocument, ESDeletedLocale
from c2corg_api.models.feed import DocumentChange, update_langs_of_changes
from c2corg_api.models.image import IMAGE_TYPE
from c2corg_api.models.route import ArchiveRoute
from c2corg_api.models.topo_map_association import TopoMapAssociation
from c2corg_api.models.user import User
from c2corg_api.models.waypoint import WAYPOINT_TYPE
from c2corg_api.search.notify_sync import notify_es_syncer
from c2corg_api.views.resource import write
from c2corg_api.views.validation import validate_id

# the version of the snapshot format
FORMAT = 1

# The tables whose rows may have lost their other end during the retention
# (an associated document deleted, a user removed): their rows are skipped
# then. The rows of the other tables are all restored, or nothing is.
OPTIONAL_TABLES = {
    table.fullname
    for table in (
        Association.__table__,
        AssociationLog.__table__,
        TopoMapAssociation.__table__,
        AreaAssociation.__table__,
        DocumentTag.__table__,
        DocumentTagLog.__table__,
        DocumentChange.__table__,
        DocumentTopic.__table__,
    )
}

# PostgreSQL takes 100 arguments at most: 2 by value of jsonb_build_object
_TEXT_VALUES_BATCH = 40


class Snapshot:
    """The rows a deletion removes, by table, and the changes it makes."""

    def __init__(self):
        self.tables = {}
        self._keys = {}
        # the archives of routes whose main waypoint is the deleted waypoint
        # (set to null by the deletion): {waypoint id: [route archive ids]}
        self.main_waypoint_of = {}

    def capture(self, model, condition):
        """Keep the rows of the table of a model that match a condition."""
        # `condition(r)` is given the aliased table `r`
        table = model.__table__
        alias = table.alias('r')
        row = func.to_jsonb(literal_column('r'), type_=JSONB)
        as_text = [c.name for c in table.columns if _kept_as_text(c)]
        for names in batched(as_text, _TEXT_VALUES_BATCH, strict=False):
            pairs = []
            for name in names:
                pairs += [cast(literal(name), Text), cast(alias.c[name], Text)]
            row = row.op('||', return_type=JSONB)(func.jsonb_build_object(*pairs))
        rows = (
            DBSession.execute(select(row).select_from(alias).where(condition(alias)))
            .scalars()
            .all()
        )
        # a row is kept once (e.g. the association of a merged document with
        # the document it was merged into)
        primary_key = [c.name for c in table.primary_key.columns]
        keys = self._keys.setdefault(table.fullname, set())
        for values in rows:
            key = tuple(values[name] for name in primary_key)
            if key not in keys:
                keys.add(key)
                self.tables.setdefault(table.fullname, []).append(values)

    def as_json(self):
        return {
            'format': FORMAT,
            'tables': self.tables,
            'main_waypoint_of': {str(k): v for k, v in self.main_waypoint_of.items()},
        }


def _kept_as_text(column):
    return isinstance(column.type, (ARRAY, Geometry))


def _models(document_type):
    # the same models as the deletion
    from c2corg_api.views.document_delete import _get_models

    return _get_models(document_type)


class _ExactFloats:
    """Floats written with all their digits while the rows are kept."""

    # Before PostgreSQL 12, a float is written with 15 digits by default:
    # not always the stored value.

    def __enter__(self):
        self._previous = DBSession.execute(
            select(func.current_setting('extra_float_digits'))
        ).scalar()
        self._set('3')

    def __exit__(self, *exc):
        self._set(self._previous)

    @staticmethod
    def _set(value):
        DBSession.execute(select(func.set_config('extra_float_digits', value, True)))


def keep_deleted_document(request, document_id, document_type):
    """Keep the rows that the deletion of a whole document removes."""
    # called before the deletion (views.document_delete._delete), with the
    # documents merged into this one, deleted with it
    snapshot = Snapshot()
    with _ExactFloats():
        _capture_document(snapshot, document_id, document_type, redirecting=False)
    _add_entry(request, snapshot, document_id, document_type, None)


def keep_deleted_locale(request, document_id, document_type, lang):
    """Keep the rows that the deletion of a locale removes."""
    # called before the deletion (views.document_delete.delete_document_locale)
    snapshot = Snapshot()
    with _ExactFloats():
        _capture_locale(snapshot, document_id, document_type, lang)
    _add_entry(request, snapshot, document_id, document_type, lang)


def _add_entry(request, snapshot, document_id, document_type, lang):
    DBSession.add(
        DeletedDocument(
            document_id=document_id,
            document_type=document_type,
            lang=lang,
            title=_title(snapshot, document_id, lang),
            deleted_by=request.authenticated_userid,
            snapshot=snapshot.as_json(),
        )
    )


def _title(snapshot, document_id, lang):
    locales = {
        row['lang']: row['title']
        for row in snapshot.tables.get(DocumentLocale.__table__.fullname, [])
        if row['document_id'] == document_id
    }
    if lang is not None:
        return locales.get(lang)
    return next((locales[lang] for lang in default_langs if lang in locales), None)


def _capture_document(snapshot, document_id, document_type, redirecting):
    # the rows views.document_delete._delete_document removes
    merged_ids = DBSession.execute(
        select(ArchiveDocument.document_id)
        .where(ArchiveDocument.redirects_to == document_id)
        .distinct()
    ).scalars()
    for merged_id in merged_ids:
        _capture_document(snapshot, merged_id, document_type, redirecting=True)

    clazz, clazz_locale, archive_clazz, archive_clazz_locale = _models(document_type)

    def of_document(r):
        return r.c.document_id == document_id

    history_ids = select(DocumentVersion.history_metadata_id).where(
        DocumentVersion.document_id == document_id
    )
    archive_ids = select(ArchiveDocument.id).where(
        ArchiveDocument.document_id == document_id
    )
    archive_locale_ids = select(ArchiveDocumentLocale.id).where(
        ArchiveDocumentLocale.document_id == document_id
    )
    locale_ids = select(DocumentLocale.id).where(
        DocumentLocale.document_id == document_id
    )

    snapshot.capture(DocumentVersion, of_document)
    snapshot.capture(HistoryMetaData, lambda r: r.c.id.in_(history_ids))
    if archive_clazz_locale:
        snapshot.capture(archive_clazz_locale, lambda r: r.c.id.in_(archive_locale_ids))
    snapshot.capture(ArchiveDocumentLocale, of_document)
    snapshot.capture(ArchiveDocumentGeometry, of_document)
    if archive_clazz is not ArchiveDocument:
        snapshot.capture(archive_clazz, lambda r: r.c.id.in_(archive_ids))
    snapshot.capture(ArchiveDocument, of_document)
    if clazz_locale:
        snapshot.capture(clazz_locale, lambda r: r.c.id.in_(locale_ids))
    snapshot.capture(DocumentTopic, lambda r: r.c.document_locale_id.in_(locale_ids))
    snapshot.capture(DocumentLocale, of_document)
    snapshot.capture(DocumentGeometry, of_document)
    snapshot.capture(clazz, of_document)
    snapshot.capture(Document, of_document)

    def of_association(r):
        return or_(
            r.c.parent_document_id == document_id,
            r.c.child_document_id == document_id,
        )

    snapshot.capture(Association, of_association)
    snapshot.capture(AssociationLog, of_association)
    snapshot.capture(TopoMapAssociation, of_document)
    snapshot.capture(AreaAssociation, of_document)
    snapshot.capture(DocumentTag, of_document)
    snapshot.capture(DocumentTagLog, of_document)
    if not redirecting:
        # Not kept: the references to a deleted image in the feed items of
        # other documents (removed or shifted by the deletion).
        snapshot.capture(DocumentChange, of_document)

    if document_type == WAYPOINT_TYPE:
        route_archive_ids = (
            DBSession.execute(
                select(ArchiveRoute.id).where(
                    ArchiveRoute.main_waypoint_id == document_id
                )
            )
            .scalars()
            .all()
        )
        if route_archive_ids:
            snapshot.main_waypoint_of[document_id] = route_archive_ids


def _capture_locale(snapshot, document_id, document_type, lang):
    # the rows views.document_delete.delete_document_locale removes; the
    # history metadata shared with other locales are kept too, and left as
    # they are when restoring
    _, clazz_locale, _, archive_clazz_locale = _models(document_type)

    def of_locale(r):
        return and_(r.c.document_id == document_id, r.c.lang == lang)

    history_ids = select(DocumentVersion.history_metadata_id).where(
        DocumentVersion.document_id == document_id, DocumentVersion.lang == lang
    )
    archive_locale_ids = select(ArchiveDocumentLocale.id).where(
        ArchiveDocumentLocale.document_id == document_id,
        ArchiveDocumentLocale.lang == lang,
    )
    locale_ids = select(DocumentLocale.id).where(
        DocumentLocale.document_id == document_id, DocumentLocale.lang == lang
    )

    snapshot.capture(DocumentVersion, of_locale)
    snapshot.capture(HistoryMetaData, lambda r: r.c.id.in_(history_ids))
    if archive_clazz_locale:
        snapshot.capture(archive_clazz_locale, lambda r: r.c.id.in_(archive_locale_ids))
    snapshot.capture(ArchiveDocumentLocale, of_locale)
    if clazz_locale:
        snapshot.capture(clazz_locale, lambda r: r.c.id.in_(locale_ids))
    snapshot.capture(DocumentTopic, lambda r: r.c.document_locale_id.in_(locale_ids))
    snapshot.capture(DocumentLocale, of_locale)


def expired_before():
    """Entries deleted before this time can no longer be restored."""
    return datetime.now(UTC) - RETENTION


def get_entry(entry_id):
    entry = DBSession.get(DeletedDocument, entry_id)
    if entry is None:
        raise HTTPNotFound(f'Unknown deleted document {entry_id}')
    return entry


def restore(request, entry):
    """Insert the rows of a deleted document or locale again."""
    _check_restorable(entry)
    tables = entry.snapshot['tables']

    skipped = {}
    for table in Base.metadata.sorted_tables:
        rows = tables.get(table.fullname)
        if not rows:
            continue
        inserted = _insert(table, rows)
        if table.fullname in OPTIONAL_TABLES:
            if inserted < len(rows):
                skipped[table.name] = len(rows) - inserted
        elif _missing(table, rows):
            # e.g. the user of a version removed since the deletion
            raise HTTPBadRequest(f'The rows of {table.name} could not all be restored')

    for waypoint_id, route_archive_ids in entry.snapshot['main_waypoint_of'].items():
        DBSession.query(ArchiveRoute).filter(
            ArchiveRoute.id.in_(route_archive_ids),
            ArchiveRoute.main_waypoint_id.is_(None),
        ).update(
            {ArchiveRoute.main_waypoint_id: int(waypoint_id)},
            synchronize_session=False,
        )

    document_id = entry.document_id
    user_id = request.authenticated_userid
    DBSession.expire_all()
    document = DBSession.get(Document, document_id)
    if entry.lang is None:
        # a deletion not yet synced would remove the document from the index
        # after it is restored
        restored_ids = [row['document_id'] for row in tables['guidebook.documents']]
        DBSession.query(ESDeletedDocument).filter(
            ESDeletedDocument.document_id.in_(restored_ids)
        ).delete(synchronize_session=False)
        langs = [locale.lang for locale in document.locales]
    else:
        DBSession.query(ESDeletedLocale).filter(
            ESDeletedLocale.document_id == document_id,
            ESDeletedLocale.lang == entry.lang,
        ).delete(synchronize_session=False)
        update_langs_of_changes(document_id)
        langs = [entry.lang]

    # a version saying who restored it, also seen by the search index sync
    # (the versions restored keep their date)
    from c2corg_api.views.document import add_unchanged_version

    add_unchanged_version(document, user_id, 'Restored', langs)
    update_cache_version_full(document_id, entry.document_type)

    missing_files = []
    if entry.document_type == IMAGE_TYPE and entry.lang is None:
        missing_files = _restore_image_files(request, tables)

    entry.restored_at = datetime.now(UTC)
    entry.restored_by = user_id

    notify_es_syncer(request.registry.queue_config)

    return {
        'document_id': document_id,
        'lang': entry.lang,
        'skipped': skipped,
        'missing_files': missing_files,
    }


def _check_restorable(entry):
    if entry.restored_at is not None:
        raise HTTPBadRequest('This document was already restored')
    if entry.deleted_at < expired_before():
        raise HTTPBadRequest('This document was deleted too long ago')
    if entry.snapshot.get('format') != FORMAT:
        raise HTTPBadRequest('Unknown format of the deleted document')

    document_exists = DBSession.query(
        exists().where(Document.document_id == entry.document_id)
    ).scalar()
    if entry.lang is None:
        ids = [
            row['document_id']
            for row in entry.snapshot['tables']['guidebook.documents']
        ]
        if DBSession.query(exists().where(Document.document_id.in_(ids))).scalar():
            raise HTTPBadRequest('The document exists')
        return

    if not document_exists:
        raise HTTPBadRequest('The document was deleted: restore it first')
    locale_exists = DBSession.query(
        exists().where(
            DocumentLocale.document_id == entry.document_id,
            DocumentLocale.lang == entry.lang,
        )
    ).scalar()
    if locale_exists:
        raise HTTPBadRequest('The locale was written again since its deletion')


def _insert(table, rows):
    """Insert kept rows; return how many were inserted."""
    # The rows whose required other end no longer exists are skipped, and the
    # optional references to rows that no longer exist set to null.
    # The columns added since the deletion take their default.
    names = [c.name for c in table.columns if any(c.name in row for row in rows)]
    record = (
        func.jsonb_populate_recordset(
            literal_column(f'NULL::{table.fullname}'),
            cast(literal(json.dumps(rows)), JSONB),
        )
        .table_valued(*names)
        .alias('r')
    )

    values = []
    conditions = []
    for name in names:
        value = record.c[name]
        for foreign_key in table.c[name].foreign_keys:
            target = foreign_key.column
            if target.table is table:
                # restored by the same statement (a merged document)
                continue
            present = exists().where(target == value)
            if table.c[name].nullable:
                value = case((present, value))
            else:
                conditions.append(present)
        values.append(value)

    if table is DocumentChange.__table__:
        # ids without foreign keys, checked by a trigger
        conditions += [
            _all_exist(record.c.user_ids, User.id),
            _all_exist(record.c.area_ids, Area.document_id),
        ]

    statement = (
        pg_insert(table)
        .from_select(names, select(*values).select_from(record).where(*conditions))
        .on_conflict_do_nothing()
    )
    return DBSession.execute(statement).rowcount


def _all_exist(ids, column):
    found = (
        select(
            func.coalesce(func.array_agg(column), cast(literal('{}'), ARRAY(Integer)))
        )
        .where(column == func.any(ids))
        .scalar_subquery()
    )
    return ids.op('<@')(found)


def _missing(table, rows):
    """How many kept rows are not in the table."""
    primary_key = list(table.primary_key.columns)
    keys = {tuple(row[c.name] for c in primary_key) for row in rows}
    found = DBSession.execute(
        select(func.count())
        .select_from(table)
        .where(tuple_(*primary_key).in_(list(keys)))
    ).scalar()
    return len(keys) - found


def _restore_image_files(request, tables):
    from c2corg_api.views.image import restore_files_of_images

    filenames = sorted(
        {
            row['filename']
            for name in ('guidebook.images', 'guidebook.images_archives')
            for row in tables.get(name, [])
            if row.get('filename')
        }
    )
    if not filenames:
        return []
    try:
        return restore_files_of_images(filenames, request)
    except Exception as e:
        raise HTTPInternalServerError('Restoring the image files failed') from e


def list_entries(offset, limit):
    """Return the deleted documents that can be restored, the last deleted first."""
    query = (
        DBSession.query(DeletedDocument, User.name, User.forum_username)
        .outerjoin(User, User.id == DeletedDocument.deleted_by)
        .filter(
            DeletedDocument.restored_at.is_(None),
            DeletedDocument.deleted_at >= expired_before(),
        )
    )
    total = query.count()
    rows = (
        query.order_by(DeletedDocument.deleted_at.desc(), DeletedDocument.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        'total': total,
        'documents': [_entry_summary(*row) for row in rows],
    }


def _entry_summary(entry, name, forum_username):
    return {
        'id': entry.id,
        'document_id': entry.document_id,
        'document_type': entry.document_type,
        'lang': entry.lang,
        'title': entry.title,
        'deleted_at': entry.deleted_at.isoformat(),
        'expires_at': (entry.deleted_at + RETENTION).isoformat(),
        'restored_at': entry.restored_at.isoformat() if entry.restored_at else None,
        'deleted_by': None
        if entry.deleted_by is None
        else {
            'user_id': entry.deleted_by,
            'name': name,
            'forum_username': forum_username,
        },
    }


def entry_details(entry):
    """Describe a deleted document: its summary, locales and the rows kept."""
    user = DBSession.get(User, entry.deleted_by) if entry.deleted_by else None
    details = _entry_summary(
        entry, user.name if user else None, user.forum_username if user else None
    )
    tables = entry.snapshot['tables']
    details['locales'] = [
        {'lang': row['lang'], 'title': row['title']}
        for row in tables.get(DocumentLocale.__table__.fullname, [])
        if row['document_id'] == entry.document_id
    ]
    details['merged_document_ids'] = sorted(
        row['document_id']
        for row in tables.get(Document.__table__.fullname, [])
        if row['document_id'] != entry.document_id
    )
    details['rows'] = {
        name.split('.', 1)[1]: len(rows) for name, rows in sorted(tables.items())
    }
    return details


# the views (routes in web.document_actions), for the moderators

LIMIT_DEFAULT = 30
LIMIT_MAX = 100


def read_deleted_documents(request):
    """List the deleted documents that can be restored.

    Request:
        `GET` `/documents/deleted?offset=0&limit=30`
    """
    offset = request.validated.get('offset', 0)
    limit = min(request.validated.get('limit', LIMIT_DEFAULT), LIMIT_MAX)
    return list_entries(offset, limit)


def read_deleted_document(request):
    """Describe a deleted document.

    Request:
        `GET` `/documents/deleted/{id}`
    """
    return entry_details(get_entry(request.validated['id']))


@write(validators=[validate_id], permission='moderator')
def restore_deleted_document(request):
    """Restore a deleted document or locale.

    Request:
        `POST` `/documents/deleted/{id}/restore`

    Response: what could not be restored, the other end of the associations,
    tags, feed items... deleted since, and the image files without a version
    left in the bucket:

        {'document_id': 123, 'lang': None,
         'skipped': {'associations': 1}, 'missing_files': []}
    """
    return restore(request, get_entry(request.validated['id']))
