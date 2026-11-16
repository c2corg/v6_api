import datetime
import json
from collections import Counter

import pytest
from httmock import HTTMock, all_requests
from sqlalchemy import Text, cast, select
from sqlalchemy.sql.expression import literal_column
from sqlalchemy.sql.functions import func

from c2corg_api.models import Base
from c2corg_api.models.deleted_document import RETENTION, DeletedDocument
from c2corg_api.models.document import (
    ArchiveDocument,
    Document,
    DocumentLocale,
    UpdateType,
)
from c2corg_api.models.document_history import DocumentVersion, HistoryMetaData
from c2corg_api.models.es_sync import ESDeletedDocument, ESDeletedLocale
from c2corg_api.models.route import ArchiveRoute
from c2corg_api.models.waypoint import WaypointLocale
from c2corg_api.tests import auth_headers

# the documents of the deletion tests
from c2corg_api.tests.views.test_document_delete import (  # noqa: F401
    _add_association,
    docs,
)
from c2corg_api.views.document import update_version

# the tables a deletion and a restoring change besides the documents
NOT_COMPARED = {
    'cache_versions',
    'es_deleted_documents',
    'es_deleted_locales',
    'es_sync_status',
    'deleted_documents',
}


def _dump(session):
    """The rows of the tables of the documents, as JSON text, by table."""
    dump = {}
    for table in Base.metadata.sorted_tables:
        if table.schema != 'guidebook' or table.name in NOT_COMPARED:
            continue
        alias = table.alias('r')
        rows = session.execute(
            select(cast(func.to_jsonb(literal_column('r')), Text)).select_from(alias)
        ).scalars()
        dump[table.name] = Counter(rows)
    return dump


def _assert_restored(before, after, restored_langs, ignored=()):
    """All rows are back, plus the version of each restored locale."""
    for name, rows in before.items():
        if name in ignored:
            continue
        missing = rows - after[name]
        assert not missing, (
            f'rows of {name} not restored: {missing} {after[name] - rows}'
        )
        added = after[name] - rows
        if name == 'history_metadata':
            assert [json.loads(row)['comment'] for row in added] == ['Restored']
        elif name == 'documents_versions':
            assert sorted(json.loads(row)['lang'] for row in added) == sorted(
                restored_langs
            )
        else:
            assert not added, f'rows added to {name}'


def _moderator():
    return auth_headers(username='moderator')


def _delete(client, document_id, lang=None):
    url = f'/documents/delete/{document_id}' + (f'/{lang}' if lang else '')
    client.delete_json(url, headers=_moderator(), status=200)


def _entry(session, document_id, lang=None):
    return (
        session.query(DeletedDocument)
        .filter(DeletedDocument.document_id == document_id)
        .filter(
            DeletedDocument.lang.is_(None)
            if lang is None
            else DeletedDocument.lang == lang
        )
        .order_by(DeletedDocument.id.desc())
        .first()
    )


def _exists(session, document_id):
    return session.query(Document).filter_by(document_id=document_id).count() > 0


def _restore(client, entry_id, status=200, username='moderator'):
    return client.post_json(
        f'/documents/deleted/{entry_id}/restore',
        {},
        headers=auth_headers(username=username),
        status=status,
    )


def _langs(session, document_id):
    return [
        lang
        for (lang,) in session.query(DocumentLocale.lang).filter(
            DocumentLocale.document_id == document_id
        )
    ]


@pytest.mark.parametrize(
    'name',
    ['waypoint3', 'route3', 'outing1', 'outing2', 'article1', 'book1', 'xreport1'],
)
def test_delete_then_restore(client, session, docs, name):  # noqa: F811
    document_id = getattr(docs, name).document_id
    langs = _langs(session, document_id)
    before = _dump(session)

    _delete(client, document_id)
    assert not _exists(session, document_id)
    entry = _entry(session, document_id)
    assert entry.deleted_by is not None

    body = _restore(client, entry.id).json

    assert body == {
        'document_id': document_id,
        'lang': None,
        'skipped': {},
        'missing_files': [],
    }
    _assert_restored(before, _dump(session), langs)
    session.expire_all()
    assert session.get(DeletedDocument, entry.id).restored_at is not None
    # not removed from the search index by a sync after the restoring
    assert session.get(ESDeletedDocument, document_id) is None


def test_restore_merged_documents(client, session, docs):  # noqa: F811
    # outing1b redirects to outing1: both are deleted, and restored
    merged_id = docs.outing1b.document_id
    _delete(client, docs.outing1.document_id)
    assert not _exists(session, merged_id)

    _restore(client, _entry(session, docs.outing1.document_id).id)

    session.expire_all()
    assert session.get(Document, merged_id).redirects_to == docs.outing1.document_id


def test_restore_former_main_waypoint(client, session, user_ids, docs):  # noqa: F811
    # the deletion removes the waypoint from the archives of the route
    for main_waypoint in (docs.waypoint3, docs.waypoint1):
        docs.route3.main_waypoint_id = main_waypoint.document_id
        session.flush()
        update_version(
            docs.route3, user_ids['contributor'], 'Update', [UpdateType.FIGURES], []
        )
    before = _dump(session)
    waypoint_id = docs.waypoint3.document_id

    _delete(client, waypoint_id)
    count = session.query(ArchiveRoute).filter(
        ArchiveRoute.main_waypoint_id == waypoint_id
    )
    assert count.count() == 0

    _restore(client, _entry(session, waypoint_id).id)

    assert count.count() == 1
    _assert_restored(before, _dump(session), ['en', 'fr'])


def test_delete_locale_then_restore(client, session, docs):  # noqa: F811
    document_id = docs.waypoint3.document_id
    before = _dump(session)

    _delete(client, document_id, 'fr')
    assert _langs(session, document_id) == ['en']
    entry = _entry(session, document_id, 'fr')
    assert entry.title == 'Mont Granier'

    body = _restore(client, entry.id).json

    assert body['lang'] == 'fr'
    assert body['skipped'] == {}
    _assert_restored(before, _dump(session), ['fr'])
    assert session.get(ESDeletedLocale, (document_id, 'fr')) is None


def test_restore_locale_with_its_own_history(client, session, user_ids, docs):  # noqa: F811
    # a translation added later has a history metadata entry of its own,
    # removed by the deletion
    docs.waypoint3.locales.append(
        WaypointLocale(lang='de', title='Granier', description='...')
    )
    session.flush()
    update_version(
        docs.waypoint3, user_ids['contributor'], 'add de', [UpdateType.LANG], ['de']
    )
    before = _dump(session)
    document_id = docs.waypoint3.document_id

    _delete(client, document_id, 'de')
    _restore(client, _entry(session, document_id, 'de').id)

    # the languages of the feed item are those of the document now (not
    # updated when the test added the locale)
    _assert_restored(before, _dump(session), ['de'], ignored={'feed_document_changes'})


def test_restore_locale_written_again(client, session, docs):  # noqa: F811
    document_id = docs.waypoint3.document_id
    _delete(client, document_id, 'fr')
    docs.waypoint3.locales.append(WaypointLocale(lang='fr', title='Granier'))
    session.flush()

    response = _restore(client, _entry(session, document_id, 'fr').id, 400)

    assert 'written again' in response.text


def test_restore_locale_of_deleted_document(client, session, docs):  # noqa: F811
    document_id = docs.waypoint3.document_id
    _delete(client, document_id, 'fr')
    _delete(client, document_id)
    locale_entry = _entry(session, document_id, 'fr')

    response = _restore(client, locale_entry.id, 400)
    assert 'restore it first' in response.text

    _restore(client, _entry(session, document_id).id)
    _restore(client, locale_entry.id)
    assert sorted(_langs(session, document_id)) == ['en', 'fr']


def test_restore_skips_the_associations_of_deleted_documents(
    client,
    session,
    user_ids,
    docs,  # noqa: F811
):
    _add_association(session, user_ids, docs.book1, docs.article1)
    session.flush()
    _delete(client, docs.article1.document_id)
    _delete(client, docs.book1.document_id)

    body = _restore(client, _entry(session, docs.article1.document_id).id).json

    assert body['skipped'] == {'associations': 1, 'association_log': 1}


def test_restore_twice(client, session, docs):  # noqa: F811
    _delete(client, docs.article1.document_id)
    entry_id = _entry(session, docs.article1.document_id).id
    _restore(client, entry_id)

    response = _restore(client, entry_id, 400)

    assert 'already restored' in response.text


def test_restore_expired(client, session, docs):  # noqa: F811
    _delete(client, docs.article1.document_id)
    entry = _entry(session, docs.article1.document_id)
    entry.deleted_at -= RETENTION + datetime.timedelta(minutes=1)
    session.flush()

    response = _restore(client, entry.id, 400)

    assert 'too long ago' in response.text


def test_restore_unknown(client):
    _restore(client, 9999999, 404)


def test_restore_requires_moderator(client, session, docs):  # noqa: F811
    _delete(client, docs.article1.document_id)
    entry_id = _entry(session, docs.article1.document_id).id

    _restore(client, entry_id, 403, username='contributor')
    client.get(
        '/documents/deleted', headers=auth_headers(username='contributor'), status=403
    )
    client.get(
        f'/documents/deleted/{entry_id}',
        headers=auth_headers(username='contributor'),
        status=403,
    )


def test_list_and_details(client, session, docs):  # noqa: F811
    _delete(client, docs.article1.document_id)
    _delete(client, docs.waypoint3.document_id, 'fr')
    _delete(client, docs.outing1.document_id)
    _restore(client, _entry(session, docs.article1.document_id).id)

    body = client.get('/documents/deleted', headers=_moderator(), status=200).json

    # the last deleted first, the restored ones not listed
    assert body['total'] == 2
    outing, locale = body['documents']
    assert outing['document_id'] == docs.outing1.document_id
    assert outing['document_type'] == 'o'
    assert outing['lang'] is None
    assert outing['deleted_by']['forum_username'] == 'moderator'
    assert locale['lang'] == 'fr'
    assert locale['title'] == 'Mont Granier'

    page = client.get(
        '/documents/deleted?offset=1&limit=1', headers=_moderator(), status=200
    ).json
    assert [d['id'] for d in page['documents']] == [locale['id']]

    details = client.get(
        f'/documents/deleted/{outing["id"]}', headers=_moderator(), status=200
    ).json
    assert details['merged_document_ids'] == [docs.outing1b.document_id]
    assert details['locales'] == [
        {'lang': row.lang, 'title': row.title} for row in docs.outing1.locales
    ]
    assert details['rows']['documents'] == 2


@all_requests
def _image_service(url, request):
    _image_service.calls.append((request.url, request.body))
    if request.url.endswith('/restore'):
        return {
            'status_code': 200,
            'content': json.dumps({'success': True, 'missing': ['image1.1.jpg']}),
        }
    return {'status_code': 200, 'content': '{"success": true}'}


def test_restore_image(client, session, settings, docs):  # noqa: F811
    document_id = docs.image1.document_id
    langs = _langs(session, document_id)
    before = _dump(session)
    _image_service.calls = []

    with HTTMock(_image_service):
        _delete(client, document_id)
        body = _restore(client, _entry(session, document_id).id).json

    url, request_body = _image_service.calls[-1]
    assert url == settings['image_backend.url'] + '/restore'
    assert 'filenames=image1.1.jpg' in request_body.split('&')
    assert 'filenames=image1.jpg' in request_body.split('&')
    assert body['missing_files'] == ['image1.1.jpg']
    # the references to the image in the feed items of other documents are
    # not restored
    _assert_restored(before, _dump(session), langs, ignored={'feed_document_changes'})


def test_restore_image_service_error(client, session, docs):  # noqa: F811
    document_id = docs.image1.document_id

    @all_requests
    def failing(url, request):
        if request.url.endswith('/restore'):
            return {'status_code': 500, 'content': ''}
        return {'status_code': 200, 'content': ''}

    with HTTMock(failing):
        _delete(client, document_id)
        _restore(client, _entry(session, document_id).id, 500)

    assert not _exists(session, document_id)
    assert (
        session.query(ArchiveDocument).filter_by(document_id=document_id).count() == 0
    )
    assert _entry(session, document_id).restored_at is None


def test_purge(client, session, docs):  # noqa: F811
    from c2corg_api.jobs.purge_deleted_documents import purge_deleted_documents

    article_id, book_id = docs.article1.document_id, docs.book1.document_id
    _delete(client, article_id)
    _delete(client, book_id)
    old = _entry(session, article_id)
    old.deleted_at -= RETENTION + datetime.timedelta(minutes=1)
    session.commit()

    purge_deleted_documents()

    session.expire_all()
    remaining = [entry.document_id for entry in session.query(DeletedDocument)]
    assert remaining == [book_id]


def test_versions_after_restore(client, session, docs):  # noqa: F811
    # the version of the restoring points to the archives of the last one
    document_id = docs.article1.document_id
    _delete(client, document_id)
    _restore(client, _entry(session, document_id).id)

    last, previous = (
        session.query(DocumentVersion)
        .filter(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.id.desc())
        .limit(2)
    )
    assert session.get(HistoryMetaData, last.history_metadata_id).comment == 'Restored'
    assert last.document_archive_id == previous.document_archive_id
    assert last.document_locales_archive_id == previous.document_locales_archive_id
