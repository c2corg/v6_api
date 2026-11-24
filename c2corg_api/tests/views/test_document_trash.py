import datetime
import json
from collections import Counter
from unittest.mock import call, patch

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
from c2corg_api.models.document_topic import DocumentTopic
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
from c2corg_api.views.document_trash import forget_user

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
        if table.name == 'feed_document_changes':
            rows = map(_sorted_langs, rows)
        dump[table.name] = Counter(rows)
    return dump


def _sorted_langs(row):
    # the langs of a feed item are recomputed by update_langs_of_changes, in
    # no given order (array_agg): ["fr", "en"] seen on PostgreSQL 9.6
    values = json.loads(row)
    values['langs'] = sorted(values['langs'] or [])
    return json.dumps(values, sort_keys=True)


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
    book_id = docs.book1.document_id
    _delete(client, docs.article1.document_id)
    _delete(client, book_id)

    entry_id = _entry(session, docs.article1.document_id).id

    details = client.get(
        f'/documents/deleted/{entry_id}', headers=_moderator(), status=200
    ).json
    book = next(a for a in details['associations'] if a['document_id'] == book_id)
    assert book == {
        'document_id': book_id,
        'document_type': 'b',
        'title': None,
        'exists': False,
    }

    body = _restore(client, entry_id).json

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
    route1_id = docs.route1.document_id
    route1_title = docs.route1.locales[0].title
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
    assert outing['author']['forum_username'] == 'contributor'
    assert outing['created_at'] is not None
    assert outing['fields'] == {
        'date_start': '2016-01-01',
        'date_end': '2016-01-01',
        'activities': ['skitouring'],
    }
    assert locale['lang'] == 'fr'
    assert locale['title'] == 'Mont Granier'
    # a deleted locale: the fields of the document, still there
    assert locale['fields'] == {'waypoint_type': 'summit', 'elevation': 3}

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
    assert details['versions'] == 1
    assert details['last_edited_by']['forum_username'] == 'contributor'
    assert [u['forum_username'] for u in details['contributors']] == ['contributor']
    route = next(a for a in details['associations'] if a['document_type'] == 'r')
    assert route == {
        'document_id': route1_id,
        'document_type': 'r',
        'title': route1_title,
        'exists': True,
    }
    assert {a['document_type'] for a in details['associations']} == {'r', 'i'}
    assert details['topics'] == [{'lang': 'en', 'topic_id': 6}]


@pytest.fixture
def topic_status(mock_topic_status):
    """The status changes of the topics in Discourse, run once committed."""
    with patch('c2corg_api.views.forum.in_background', side_effect=lambda op: op()):
        yield mock_topic_status


def test_topics_hidden_then_shown(client, session, docs, topic_status):  # noqa: F811
    _delete(client, docs.waypoint3.document_id)

    assert topic_status.call_args_list == [
        call(2, 'closed', True),
        call(2, 'visible', False),
        call(3, 'closed', True),
        call(3, 'visible', False),
    ]

    topic_status.reset_mock()
    _restore(client, _entry(session, docs.waypoint3.document_id).id)

    assert topic_status.call_args_list == [
        call(2, 'closed', False),
        call(2, 'visible', True),
        call(3, 'closed', False),
        call(3, 'visible', True),
    ]


def test_topic_of_deleted_locale_hidden(client, session, docs, topic_status):  # noqa: F811
    _delete(client, docs.waypoint3.document_id, 'fr')

    assert topic_status.call_args_list == [
        call(3, 'closed', True),
        call(3, 'visible', False),
    ]


def test_topics_forum_error(client, session, docs, topic_status):  # noqa: F811
    # the deletion is kept, the topics stay as they were
    topic_status.side_effect = ConnectionError()
    _delete(client, docs.waypoint3.document_id)

    assert not _exists(session, docs.waypoint3.document_id)
    assert topic_status.call_count == 2


def test_no_topic_no_forum_call(client, session, docs, topic_status):  # noqa: F811
    session.query(DocumentTopic).delete()
    _delete(client, docs.article1.document_id)

    topic_status.assert_not_called()


def test_list_filters(client, session, user_ids, docs):  # noqa: F811
    _delete(client, docs.article1.document_id)
    _delete(client, docs.waypoint3.document_id, 'fr')
    _delete(client, docs.outing1.document_id)
    contributor, moderator = user_ids['contributor'], user_ids['moderator']
    # deleted before
    _entry(session, docs.article1.document_id).deleted_at = datetime.datetime(
        2026, 11, 2, 12, tzinfo=datetime.UTC
    )
    session.flush()
    today = datetime.datetime.now(datetime.UTC).date()

    def listed(query):
        body = client.get(
            '/documents/deleted?' + query, headers=_moderator(), status=200
        ).json
        assert body['total'] == len(body['documents'])
        return [(d['document_id'], d['lang']) for d in body['documents']]

    assert _entry(session, docs.outing1.document_id).author_id == contributor
    assert listed('type=o') == [(docs.outing1.document_id, None)]
    assert listed(f'author={contributor}&type=w') == [
        (docs.waypoint3.document_id, 'fr')
    ]
    assert listed(f'deleted_by={contributor}') == []
    assert len(listed(f'deleted_by={moderator}')) == 3
    assert listed('deleted_since=2026-11-01&deleted_until=2026-11-02') == [
        (docs.article1.document_id, None)
    ]
    assert len(listed(f'deleted_since={today}')) == 2
    assert listed('deleted_until=2026-11-01') == []

    for query in ('type=q', 'author=me', 'deleted_since=yesterday'):
        client.get('/documents/deleted?' + query, headers=_moderator(), status=422)


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


def test_delete_without_keeping(client, session, settings, queue_config, docs):  # noqa: F811
    from types import SimpleNamespace

    from c2corg_api.views.document_delete import _delete as delete

    # as a script deletes: no user, nothing kept
    document_id = docs.article1.document_id
    request = SimpleNamespace(
        registry=SimpleNamespace(settings=settings, queue_config=queue_config)
    )
    delete(request, document_id, 'c', keep=False)

    assert not _exists(session, document_id)
    assert _entry(session, document_id) is None


def test_forget_user_alone(client, session, user_ids, docs):  # noqa: F811
    # a document only this user wrote: removed with the account
    document_id = docs.outing1.document_id
    _delete(client, document_id)

    assert forget_user(user_ids['contributor'], user_ids['moderator']) == (1, 0)

    assert _entry(session, document_id) is None


def test_forget_user_with_others(client, session, user_ids, docs):  # noqa: F811
    # also written by another user: the user becomes the target user, the
    # document can still be restored
    contributor, moderator = user_ids['contributor'], user_ids['moderator']
    docs.article1.locales[0].title = 'Edited'
    session.flush()
    update_version(docs.article1, moderator, 'edit', [UpdateType.LANG], ['en'])
    document_id = docs.article1.document_id
    _delete(client, document_id)

    assert forget_user(contributor, user_ids['contributor2']) == (0, 1)

    session.expire_all()
    entry = _entry(session, document_id)
    authors = {
        row['user_id'] for row in entry.snapshot['tables']['guidebook.history_metadata']
    }
    assert authors == {user_ids['contributor2'], moderator}
    assert entry.author_id == user_ids['contributor2']
    _restore(client, entry.id)
    history = session.query(HistoryMetaData.user_id).join(
        DocumentVersion, DocumentVersion.history_metadata_id == HistoryMetaData.id
    )
    assert contributor not in {
        user_id
        for (user_id,) in history.filter(DocumentVersion.document_id == document_id)
    }


def test_forget_user_others_untouched(client, session, user_ids, docs):  # noqa: F811
    _delete(client, docs.outing1.document_id)

    assert forget_user(user_ids['moderator'], user_ids['contributor']) == (0, 0)

    assert _entry(session, docs.outing1.document_id) is not None


def test_merge_user_accounts(client, session, user_ids, queue_config, docs):  # noqa: F811
    from c2corg_api.scripts.users.merge import merge_user_accounts

    document_id = docs.outing1.document_id
    _delete(client, document_id)

    merge_user_accounts(user_ids['contributor'], user_ids['contributor2'], queue_config)

    assert _entry(session, document_id) is None


def _image(session, user_ids, username, image_type, linked_to, title):
    """Add an image created by a user, linked to the given documents."""
    from c2corg_api.models.image import Image
    from c2corg_api.tests.views.test_document_delete import _add_association
    from c2corg_api.views.document import create_new_version

    image = Image(
        filename=f'{title}.jpg',
        image_type=image_type,
        locales=[DocumentLocale(lang='en', title=title)],
    )
    session.add(image)
    session.flush()
    create_new_version(image, user_ids[username])
    for document in linked_to:
        _add_association(session, user_ids, document, image)
    session.flush()
    return image


@pytest.fixture
def outing_images(session, user_ids, docs):  # noqa: F811
    """Images of outing2 (created by contributor): only `photo` goes with it."""
    from c2corg_api.models.feed import update_feed_images_upload

    outing = docs.outing2
    images = {
        # personal, by the author of the outing, linked to the outing only
        'photo': _image(
            session, user_ids, 'contributor', 'personal', [outing], 'photo'
        ),
        # also linked to a route
        'shared': _image(
            session,
            user_ids,
            'contributor',
            'personal',
            [outing, docs.route3],
            'shared',
        ),
        'collaborative': _image(
            session, user_ids, 'contributor', 'collaborative', [outing], 'collab'
        ),
        # by another user
        'other': _image(
            session, user_ids, 'contributor2', 'personal', [outing], 'other'
        ),
    }
    update_feed_images_upload(
        [images['photo']],
        [
            {
                'filename': 'photo.jpg',
                'image_type': 'personal',
                'locales': [{'lang': 'en', 'title': 'photo'}],
                'associations': {'outings': [{'document_id': outing.document_id}]},
            }
        ],
        user_ids['contributor'],
    )
    session.flush()
    return images


def test_personal_images_deleted_with_document(
    client,
    session,
    settings,
    outing_images,
    docs,  # noqa: F811
):
    outing_id = docs.outing2.document_id
    photo_id = outing_images['photo'].document_id
    before = _dump(session)
    _image_service.calls = []

    with HTTMock(_image_service):
        _delete(client, outing_id)

        assert not _exists(session, photo_id)
        for name in ('shared', 'collaborative', 'other'):
            assert _exists(session, outing_images[name].document_id), name
        # one entry for the outing and its images, the files deleted
        assert _entry(session, photo_id) is None
        entry = _entry(session, outing_id)
        assert entry.snapshot['deleted_images'] == [photo_id]
        assert session.get(ESDeletedDocument, photo_id) is not None
        url, request_body = _image_service.calls[0]
        assert url == settings['image_backend.url'] + '/delete'
        assert 'filenames=photo.jpg' in request_body.split('&')

        listed = client.get('/documents/deleted', headers=_moderator()).json
        assert listed['documents'][0]['deleted_images'] == 1
        details = client.get(
            f'/documents/deleted/{entry.id}', headers=_moderator()
        ).json
        assert details['deleted_images'] == [
            {'document_id': photo_id, 'title': 'photo', 'filename': 'photo.jpg'}
        ]
        assert details['merged_document_ids'] == []
        assert photo_id not in {a['document_id'] for a in details['associations']}

        body = _restore(client, entry.id).json

    url, request_body = _image_service.calls[-1]
    assert url == settings['image_backend.url'] + '/restore'
    assert 'filenames=photo.jpg' in request_body.split('&')
    assert body['skipped'] == {}
    # the outing, the image, their link and the feed item are back, with a
    # version of each saying it was restored
    _assert_restored(before, _dump(session), ['en', 'en'], ignored={'history_metadata'})
    session.expire_all()
    assert session.get(ESDeletedDocument, photo_id) is None


def test_images_kept_when_deleted_by_their_author(
    client,
    session,
    user_ids,
    outing_images,
    docs,  # noqa: F811
):
    # the author of the outing deletes it: their photo goes with it
    with HTTMock(_image_service):
        client.delete_json(
            f'/documents/delete/{docs.outing2.document_id}',
            headers=auth_headers(username='contributor'),
            status=200,
        )

    assert not _exists(session, outing_images['photo'].document_id)
    assert _exists(session, outing_images['other'].document_id)


def test_no_image_deleted_without_keeping(
    client,
    session,
    settings,
    queue_config,
    outing_images,
    docs,  # noqa: F811
):
    from types import SimpleNamespace

    from c2corg_api.views.document_delete import _delete as delete

    request = SimpleNamespace(
        registry=SimpleNamespace(settings=settings, queue_config=queue_config)
    )
    with HTTMock(_image_service):
        delete(request, docs.outing2.document_id, 'o', keep=False)

    assert _exists(session, outing_images['photo'].document_id)


def test_no_image_deleted_with_an_image(client, session, user_ids, docs):  # noqa: F811
    linked = _image(session, user_ids, 'contributor', 'personal', [], 'linked')
    _image(session, user_ids, 'contributor', 'personal', [linked], 'child')
    child_id = session.query(DocumentLocale.document_id).filter_by(title='child')
    with HTTMock(_image_service):
        _delete(client, linked.document_id)

    assert _exists(session, child_id.scalar())


def test_images_of_deletion(client, outing_images, docs):  # noqa: F811
    url = f'/documents/delete/{docs.outing2.document_id}/images'
    expected = {
        'deleted': 1,
        # the collaborative image, and the personal one of another user
        'orphaned': {'collaborative': 1, 'personal': 1, 'copyright': 0},
    }

    for username in ('moderator', 'contributor'):
        body = client.get(url, headers=auth_headers(username=username)).json
        assert body == expected, username

    # who may not delete the document may not ask either
    client.get(url, headers=auth_headers(username='contributor2'), status=400)
    client.get(url, status=403)
    client.get('/documents/delete/9999999/images', headers=_moderator(), status=404)


def test_images_of_deletion_of_an_image(client, docs):  # noqa: F811
    url = f'/documents/delete/{docs.image1.document_id}/images'
    body = client.get(url, headers=_moderator()).json
    assert body == {
        'deleted': 0,
        'orphaned': {'collaborative': 0, 'personal': 0, 'copyright': 0},
    }
