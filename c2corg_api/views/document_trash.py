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
from datetime import UTC, datetime, timedelta
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
from c2corg_api.models.common.document_types import (
    ARTICLE_TYPE,
    BOOK_TYPE,
    IMAGE_TYPE,
    OUTING_TYPE,
    ROUTE_TYPE,
    USERPROFILE_TYPE,
    XREPORT_TYPE,
)
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
    entry = DeletedDocument(
        document_id=document_id,
        document_type=document_type,
        lang=lang,
        title=_title(snapshot, document_id, lang),
        deleted_by=request.authenticated_userid,
        snapshot=snapshot.as_json(),
    )
    entry.author_id = _history(entry)['author_id']
    DBSession.add(entry)


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


# the fields shown with a deleted document, by type
KEY_FIELDS = {
    OUTING_TYPE: ('date_start', 'date_end', 'activities'),
    ROUTE_TYPE: ('activities', 'elevation_max'),
    WAYPOINT_TYPE: ('waypoint_type', 'elevation'),
    ARTICLE_TYPE: ('article_type', 'activities'),
    BOOK_TYPE: ('book_types', 'author'),
    XREPORT_TYPE: ('date', 'event_type', 'event_activity'),
    IMAGE_TYPE: ('image_type', 'date_time', 'activities'),
}


def list_entries(
    offset,
    limit,
    document_type=None,
    author_id=None,
    deleted_by=None,
    deleted_since=None,
    deleted_until=None,
):
    """Return the deleted documents that can be restored, the last deleted first."""
    # deleted_since and deleted_until are days, both included
    query = DBSession.query(DeletedDocument).filter(
        DeletedDocument.restored_at.is_(None),
        DeletedDocument.deleted_at >= expired_before(),
    )
    if document_type is not None:
        query = query.filter(DeletedDocument.document_type == document_type)
    if author_id is not None:
        query = query.filter(DeletedDocument.author_id == author_id)
    if deleted_by is not None:
        query = query.filter(DeletedDocument.deleted_by == deleted_by)
    if deleted_since is not None:
        query = query.filter(DeletedDocument.deleted_at >= _start_of(deleted_since))
    if deleted_until is not None:
        query = query.filter(
            DeletedDocument.deleted_at < _start_of(deleted_until + timedelta(days=1))
        )
    total = query.count()
    entries = (
        query.order_by(DeletedDocument.deleted_at.desc(), DeletedDocument.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    histories = {entry.id: _history(entry) for entry in entries}
    users = _users(
        user_id
        for entry in entries
        for user_id in (entry.deleted_by, histories[entry.id]['author_id'])
    )
    return {
        'total': total,
        'documents': [
            _entry_summary(entry, histories[entry.id], users) for entry in entries
        ],
    }


def _start_of(day):
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def _entry_summary(entry, history, users):
    return {
        'id': entry.id,
        'document_id': entry.document_id,
        'document_type': entry.document_type,
        'lang': entry.lang,
        'title': entry.title,
        # who wrote the document (the locale when a locale was deleted), when
        'author': _user(users, history['author_id']),
        'created_at': history['created_at'],
        'fields': _key_fields(entry),
        'deleted_at': entry.deleted_at.isoformat(),
        'deleted_by': _user(users, entry.deleted_by),
        'expires_at': (entry.deleted_at + RETENTION).isoformat(),
        'restored_at': entry.restored_at.isoformat() if entry.restored_at else None,
    }


def _rows(entry, model):
    return entry.snapshot['tables'].get(model.__table__.fullname, [])


def _history(entry):
    """Return the versions of the deleted document or locale, from the kept rows."""
    version_rows = [
        row
        for row in _rows(entry, DocumentVersion)
        if row['document_id'] == entry.document_id
        and (entry.lang is None or row['lang'] == entry.lang)
    ]
    ids = {row['history_metadata_id'] for row in version_rows}
    changes = sorted(
        (
            (datetime.fromisoformat(row['written_at']), row['user_id'])
            for row in _rows(entry, HistoryMetaData)
            if row['id'] in ids
        ),
        key=lambda change: change[0],
    )
    first, last = (changes[0], changes[-1]) if changes else ((None, None),) * 2
    return {
        'author_id': first[1],
        'created_at': first[0].isoformat() if first[0] else None,
        'last_edited_by_id': last[1],
        'last_edited_at': last[0].isoformat() if last[0] else None,
        'versions': len(changes),
        'contributor_ids': sorted({user_id for _, user_id in changes}),
    }


def _key_fields(entry):
    names = KEY_FIELDS.get(entry.document_type, ())
    if entry.lang is not None:
        # a deleted locale: the fields of the document, still there
        document = DBSession.get(Document, entry.document_id)
        return {name: _json_value(getattr(document, name, None)) for name in names}
    clazz = _models(entry.document_type)[0]
    row = next(
        (r for r in _rows(entry, clazz) if r['document_id'] == entry.document_id),
        {},
    )
    return {name: _kept_value(row.get(name)) for name in names}


def _json_value(value):
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return value


def _kept_value(value):
    # the arrays are kept in the text form of PostgreSQL: {a,b}
    if isinstance(value, str) and value.startswith('{') and value.endswith('}'):
        return [item for item in value[1:-1].split(',') if item]
    return value


def _users(ids):
    """Return the users of the given ids, by id."""
    ids = {user_id for user_id in ids if user_id is not None}
    if not ids:
        return {}
    rows = DBSession.query(User.id, User.name, User.forum_username).filter(
        User.id.in_(ids)
    )
    return {
        user_id: {'user_id': user_id, 'name': name, 'forum_username': forum_username}
        for user_id, name, forum_username in rows
    }


def _user(users, user_id):
    if user_id is None:
        return None
    # a user removed since: only the id
    return users.get(
        user_id, {'user_id': user_id, 'name': None, 'forum_username': None}
    )


def entry_details(entry):
    """Describe a deleted document: its summary, history, links and the rows kept."""
    history = _history(entry)
    associations = _associations(entry)
    users = _users(
        [entry.deleted_by, history['author_id'], history['last_edited_by_id']]
        + history['contributor_ids']
    )
    details = _entry_summary(entry, history, users)
    locale_rows = [
        row
        for row in _rows(entry, DocumentLocale)
        if row['document_id'] == entry.document_id
    ]
    details['locales'] = [
        {'lang': row['lang'], 'title': row['title']} for row in locale_rows
    ]
    details['last_edited_by'] = _user(users, history['last_edited_by_id'])
    details['last_edited_at'] = history['last_edited_at']
    details['versions'] = history['versions']
    details['contributors'] = [
        _user(users, user_id) for user_id in history['contributor_ids']
    ]
    details['associations'] = associations
    # the comments stay in the forum: their topics, by language
    langs = {row['id']: row['lang'] for row in locale_rows}
    details['topics'] = [
        {'lang': langs[row['document_locale_id']], 'topic_id': row['topic_id']}
        for row in _rows(entry, DocumentTopic)
        if row['document_locale_id'] in langs
    ]
    details['merged_document_ids'] = sorted(
        row['document_id']
        for row in _rows(entry, Document)
        if row['document_id'] != entry.document_id
    )
    details['rows'] = {
        name.split('.', 1)[1]: len(rows)
        for name, rows in sorted(entry.snapshot['tables'].items())
    }
    return details


def _associations(entry):
    """Return the documents the deleted document was linked to, as they are now."""
    linked = {}
    for row in _rows(entry, Association):
        if row['parent_document_id'] == entry.document_id:
            linked[row['child_document_id']] = row['child_document_type']
        elif row['child_document_id'] == entry.document_id:
            linked[row['parent_document_id']] = row['parent_document_type']
    if not linked:
        return []
    existing = set(
        DBSession.execute(
            select(Document.document_id).where(Document.document_id.in_(linked))
        ).scalars()
    )
    titles = {}
    for document_id, lang, title in DBSession.query(
        DocumentLocale.document_id, DocumentLocale.lang, DocumentLocale.title
    ).filter(DocumentLocale.document_id.in_(existing)):
        titles.setdefault(document_id, {})[lang] = title
    users = _users(
        document_id
        for document_id, document_type in linked.items()
        if document_type == USERPROFILE_TYPE
    )
    result = []
    for document_id, document_type in sorted(linked.items()):
        if document_type == USERPROFILE_TYPE:
            # the title of a user profile is the name of the user
            title = users.get(document_id, {}).get('name')
        else:
            by_lang = titles.get(document_id, {})
            title = next(
                (by_lang[lang] for lang in default_langs if lang in by_lang), None
            )
        result.append(
            {
                'document_id': document_id,
                'document_type': document_type,
                'title': title,
                # linked to a document deleted since: no title
                'exists': document_id in existing,
            }
        )
    return result


# the views (routes in web.document_actions), for the moderators

LIMIT_DEFAULT = 30
LIMIT_MAX = 100


def read_deleted_documents(request):
    """List the deleted documents that can be restored.

    Request:
        `GET` `/documents/deleted?offset=0&limit=30`

        Filters: `type` (`o`...), `author` and `deleted_by` (user ids),
        `deleted_since` and `deleted_until` (days, YYYY-MM-DD, included).
    """
    validated = request.validated
    return list_entries(
        validated.get('offset') or 0,
        min(validated.get('limit') or LIMIT_DEFAULT, LIMIT_MAX),
        document_type=validated.get('type'),
        author_id=validated.get('author'),
        deleted_by=validated.get('deleted_by'),
        deleted_since=validated.get('deleted_since'),
        deleted_until=validated.get('deleted_until'),
    )


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


def forget_user(user_id, target_user_id):
    """Remove or rewrite the deleted documents keeping a user being removed."""
    # Called when an account is merged into another, which removes it
    # (scripts/users/merge.py, the account removal requests): the deleted
    # documents only this user wrote are removed with the account; in the
    # others, the user becomes the target user, as in the tables of the
    # documents, so that they can still be restored. Returns (removed,
    # rewritten).
    removed = rewritten = 0
    for entry in DBSession.query(DeletedDocument).all():
        if user_id not in _kept_user_ids(entry):
            continue
        if _history(entry)['contributor_ids'] == [user_id]:
            DBSession.delete(entry)
            removed += 1
            continue
        snapshot = json.loads(json.dumps(entry.snapshot))
        _replace_user(snapshot['tables'], user_id, target_user_id)
        entry.snapshot = snapshot
        entry.author_id = _history(entry)['author_id']
        rewritten += 1
    DBSession.flush()
    return removed, rewritten


# the columns of the kept rows holding a user id
_USER_COLUMNS = {
    HistoryMetaData.__table__.fullname: ('user_id',),
    AssociationLog.__table__.fullname: ('user_id',),
    DocumentTag.__table__.fullname: ('user_id',),
    DocumentTagLog.__table__.fullname: ('user_id',),
    DocumentChange.__table__.fullname: ('user_id',),
}


def _kept_user_ids(entry):
    tables = entry.snapshot['tables']
    ids = {
        row[column]
        for name, columns in _USER_COLUMNS.items()
        for row in tables.get(name, [])
        for column in columns
    }
    for row in tables.get(DocumentChange.__table__.fullname, []):
        ids.update(int(i) for i in _kept_value(row['user_ids']) or [])
    for name in (Association.__table__.fullname, AssociationLog.__table__.fullname):
        for row in tables.get(name, []):
            for side in ('parent', 'child'):
                if row[f'{side}_document_type'] == USERPROFILE_TYPE:
                    ids.add(row[f'{side}_document_id'])
    return ids


def _replace_user(tables, user_id, target_user_id):
    for name, columns in _USER_COLUMNS.items():
        for row in tables.get(name, []):
            for column in columns:
                if row[column] == user_id:
                    row[column] = target_user_id
    for row in tables.get(DocumentChange.__table__.fullname, []):
        ids = [int(i) for i in _kept_value(row['user_ids']) or []]
        if user_id in ids:
            ids = list(
                dict.fromkeys(target_user_id if i == user_id else i for i in ids)
            )
            row['user_ids'] = '{' + ','.join(str(i) for i in ids) + '}'
    # the user profile of the user (outing participants...)
    for name in (Association.__table__.fullname, AssociationLog.__table__.fullname):
        for row in tables.get(name, []):
            for side in ('parent', 'child'):
                if (
                    row[f'{side}_document_type'] == USERPROFILE_TYPE
                    and row[f'{side}_document_id'] == user_id
                ):
                    row[f'{side}_document_id'] = target_user_id
