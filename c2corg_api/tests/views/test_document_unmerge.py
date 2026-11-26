import datetime
import json
from collections import Counter

import pytest
from httmock import HTTMock, all_requests
from sqlalchemy import Text, cast, select
from sqlalchemy.sql.expression import literal_column
from sqlalchemy.sql.functions import func

from c2corg_api.models.article import Article
from c2corg_api.models.association import Association, AssociationLog
from c2corg_api.models.deleted_document import RETENTION, DeletedDocument
from c2corg_api.models.document import ArchiveDocument, Document, DocumentLocale
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.favourite import Favourite, FavouriteLog
from c2corg_api.models.feed import DocumentChange
from c2corg_api.models.merged_document import MergedDocument
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.tests import auth_headers
from c2corg_api.tests.views.test_document_merge import docs  # noqa: F401
from c2corg_api.views.document import create_new_version

# the tables a merge changes, besides the documents and their versions
CHANGED = (
    Association,
    AssociationLog,
    Favourite,
    FavouriteLog,
    DocumentChange,
    Route,
    RouteLocale,
)


def _dump(session):
    """The rows of the tables a merge changes, as JSON text, by table."""
    dump = {}
    for model in CHANGED:
        alias = model.__table__.alias('r')
        rows = session.execute(
            select(cast(func.to_jsonb(literal_column('r')), Text)).select_from(alias)
        ).scalars()
        dump[model.__tablename__] = Counter(rows)
    return dump


def _moderator():
    return auth_headers(username='moderator')


def _merge(client, source, target):
    client.post_json(
        '/documents/merge',
        {
            'source_document_id': source.document_id,
            'target_document_id': target.document_id,
        },
        headers=_moderator(),
        status=200,
    )


def _entry(session, source):
    return (
        session.query(MergedDocument)
        .filter(MergedDocument.source_document_id == source.document_id)
        .order_by(MergedDocument.id.desc())
        .first()
    )


def _unmerge(client, entry_id, status=200, username='moderator'):
    return client.post_json(
        f'/documents/merged/{entry_id}/unmerge',
        {},
        headers=auth_headers(username=username),
        status=status,
    )


def _redirects_to(session, document):
    return session.execute(
        select(Document.redirects_to).where(
            Document.document_id == document.document_id
        )
    ).scalar()


def test_unmerge_waypoint(client, session, docs):  # noqa: F811
    before = _dump(session)
    _merge(client, docs.waypoint1, docs.waypoint2)
    assert _dump(session) != before
    entry = _entry(session, docs.waypoint1)
    assert entry.target_document_id == docs.waypoint2.document_id
    # waypoint4 is linked with both: that association is removed, not moved
    assert len(entry.snapshot['associations']) == 2
    assert len(entry.snapshot['removed']['guidebook.associations']) == 1

    body = _unmerge(client, entry.id).json

    assert body['skipped'] == {}
    assert body['missing_files'] == []
    # the associations, their logs, the main waypoint of the routes, the
    # title prefix of the routes, the feed entry: all as before the merge
    # (the dates of the logs too: one transaction in the tests)
    after = _dump(session)
    # the fixture sets no title prefix, the unmerge sets it from waypoint1
    del before['routes_locales'], after['routes_locales']
    assert after == before
    session.refresh(docs.route1)
    assert docs.route1.main_waypoint_id == docs.waypoint1.document_id
    assert docs.route1.locales[0].title_prefix == 'Dent de Crolles'
    assert _redirects_to(session, docs.waypoint1) is None
    # merged into waypoint1 before the merge: redirects to it again
    assert _redirects_to(session, docs.waypoint3) == docs.waypoint1.document_id
    comment = (
        session.query(DocumentVersion)
        .filter(DocumentVersion.document_id == docs.waypoint1.document_id)
        .order_by(DocumentVersion.id.desc())
        .first()
        .history_metadata.comment
    )
    assert comment == f'unmerged from {docs.waypoint2.document_id}'
    session.refresh(entry)
    assert entry.unmerged_at is not None
    assert entry.unmerged_by is not None


def test_unmerge_favourites(client, session, docs):  # noqa: F811
    before = _dump(session)
    _merge(client, docs.route1, docs.route2)
    assert (
        session.query(Favourite)
        .filter(Favourite.document_id == docs.route2.document_id)
        .count()
        == 1
    )

    _unmerge(client, _entry(session, docs.route1).id)

    assert _dump(session) == before


def test_change_since_merge_kept(client, session, docs, user_ids):  # noqa: F811
    _merge(client, docs.waypoint1, docs.waypoint2)
    entry = _entry(session, docs.waypoint1)
    # after the merge, a contributor removes the moved association with
    # route1 and adds it again: it belongs to the target now
    later = entry.merged_at + datetime.timedelta(minutes=1)
    for is_creation in (False, True):
        session.add(
            AssociationLog(
                parent_document_id=docs.waypoint2.document_id,
                parent_document_type='w',
                child_document_id=docs.route1.document_id,
                child_document_type='r',
                user_id=user_ids['contributor'],
                is_creation=is_creation,
                written_at=later,
            )
        )
    session.flush()

    body = _unmerge(client, entry.id).json

    assert body['skipped'] == {'associations': 1}
    assert _associated(session, docs.waypoint2, docs.route1)
    assert not _associated(session, docs.waypoint1, docs.route1)
    assert _associated(session, docs.waypoint1, docs.route2)


def test_association_removed_since_merge(client, session, docs):  # noqa: F811
    _merge(client, docs.waypoint1, docs.waypoint2)
    session.query(Association).filter(
        Association.parent_document_id == docs.waypoint2.document_id,
        Association.child_document_id == docs.route2.document_id,
    ).delete()
    session.flush()

    body = _unmerge(client, _entry(session, docs.waypoint1).id).json

    assert body['skipped'] == {'associations': 1}


@all_requests
def _image_service(url, request):
    _image_service.calls.append((request.url, request.body))
    if request.url.endswith('/restore'):
        return {
            'status_code': 200,
            'content': json.dumps({'success': True, 'missing': []}),
        }
    return {'status_code': 200, 'content': '{"success": true}'}


def test_unmerge_image(client, session, settings, docs):  # noqa: F811
    _image_service.calls = []
    with HTTMock(_image_service):
        _merge(client, docs.image1, docs.image2)
        _unmerge(client, _entry(session, docs.image1).id)

    url, request_body = _image_service.calls[-1]
    assert url == settings['image_backend.url'] + '/restore'
    assert 'filenames=image1.1.jpg' in request_body.split('&')
    assert 'filenames=image1.jpg' in request_body.split('&')
    assert _redirects_to(session, docs.image1) is None


def test_unmerge_twice(client, session, docs):  # noqa: F811
    _merge(client, docs.route1, docs.route2)
    entry_id = _entry(session, docs.route1).id
    _unmerge(client, entry_id)
    _unmerge(client, entry_id, status=400)


def test_target_merged_since(client, session, docs, user_ids):  # noqa: F811
    # a merge writes a version of the source: the fixture gives none to these
    create_new_version(docs.waypoint2, user_ids['contributor'])
    session.flush()
    _merge(client, docs.waypoint1, docs.waypoint2)
    _merge(client, docs.waypoint2, docs.waypoint4)
    _unmerge(client, _entry(session, docs.waypoint1).id, status=400)

    # undone in the reverse order
    _unmerge(client, _entry(session, docs.waypoint2).id)
    _unmerge(client, _entry(session, docs.waypoint1).id)
    assert _redirects_to(session, docs.waypoint1) is None
    assert _redirects_to(session, docs.waypoint2) is None


def test_expired(client, session, docs):  # noqa: F811
    _merge(client, docs.route1, docs.route2)
    entry = _entry(session, docs.route1)
    entry.merged_at = entry.merged_at - RETENTION - datetime.timedelta(minutes=1)
    session.flush()
    _unmerge(client, entry.id, status=400)


def test_moderators_only(client, session, docs):  # noqa: F811
    _merge(client, docs.route1, docs.route2)
    entry_id = _entry(session, docs.route1).id
    _unmerge(client, entry_id, status=403, username='contributor')
    _unmerge(client, 999999, status=404)
    client.get('/documents/deleted?kind=merged', status=403)


def _list(client, query=''):
    return client.get(
        '/documents/deleted?' + query, headers=_moderator(), status=200
    ).json


def test_list_with_deletions(client, session, docs, user_ids):  # noqa: F811
    _merge(client, docs.route1, docs.route2)
    client.delete_json(
        f'/documents/delete/{docs.waypoint4.document_id}',
        headers=_moderator(),
        status=200,
    )

    body = _list(client)
    assert body['total'] == 2
    # the last first: one transaction in the tests, same date, then by kind
    deleted, merged = body['documents']
    assert deleted['kind'] == 'deleted'
    assert deleted['document_id'] == docs.waypoint4.document_id
    assert merged['kind'] == 'merged'
    assert merged['document_id'] == docs.route1.document_id
    assert merged['document_type'] == 'r'
    assert merged['title'] == 'Mont Blanc du ciel'
    assert merged['target_document_id'] == docs.route2.document_id
    assert merged['target_title'] == 'Mont Blanc du soleil'
    assert merged['deleted_by']['name'] == 'Moderator'
    assert merged['author']['user_id'] == user_ids['contributor']
    assert merged['counts']['favourites_moved'] == 1

    # the filters
    def kinds(query):
        return [entry['kind'] for entry in _list(client, query)['documents']]

    assert kinds('kind=merged') == ['merged']
    assert kinds('kind=deleted') == ['deleted']
    assert kinds('type=r') == ['merged']
    assert kinds('type=w') == ['deleted']
    assert kinds(f'author={user_ids["contributor"]}') == ['merged']
    assert kinds(f'deleted_by={user_ids["moderator"]}') == ['deleted', 'merged']
    assert kinds(f'deleted_by={user_ids["contributor"]}') == []
    assert kinds('deleted_until=2026-01-01') == []
    assert kinds('kind=merged&deleted_since=2026-01-01') == ['merged']
    client.get('/documents/deleted?kind=both', headers=_moderator(), status=422)

    # paging over both kinds
    body = _list(client, 'offset=1&limit=1')
    assert body['total'] == 2
    assert [entry['kind'] for entry in body['documents']] == ['merged']

    _unmerge(client, merged['id'])
    assert kinds('') == ['deleted']


# with the soft delete (views.document_trash): a deleted target or source
# takes the merge out of the list, its restore brings it back


def _delete(client, document):
    client.delete_json(
        f'/documents/delete/{document.document_id}', headers=_moderator(), status=200
    )


def _restore(client, session, document):
    entry = (
        session.query(DeletedDocument)
        .filter(
            DeletedDocument.document_id == document.document_id,
            DeletedDocument.lang.is_(None),
        )
        .order_by(DeletedDocument.id.desc())
        .first()
    )
    return client.post_json(
        f'/documents/deleted/{entry.id}/restore', {}, headers=_moderator(), status=200
    ).json


def _listed(client):
    body = _list(client, 'kind=merged')
    assert body['total'] == len(body['documents'])
    return [merge['document_id'] for merge in body['documents']]


def _exists(session, document):
    # a query: session.get would answer from the identity map
    return (
        session.query(Document)
        .filter(Document.document_id == document.document_id)
        .count()
        > 0
    )


def _archives_redirecting(session, document, target):
    return (
        session.query(ArchiveDocument)
        .filter(
            ArchiveDocument.document_id == document.document_id,
            ArchiveDocument.redirects_to == target.document_id,
        )
        .count()
    )


def _associated(session, parent, child):
    return (
        session.query(Association)
        .filter(
            Association.parent_document_id == parent.document_id,
            Association.child_document_id == child.document_id,
        )
        .count()
        > 0
    )


@pytest.fixture
def route0(session, docs):  # noqa: F811
    # merged into route1 before
    route = Route(
        activities=['skitouring'],
        redirects_to=docs.route1.document_id,
        locales=[RouteLocale(lang='fr', title='Mont Blanc de la lune')],
    )
    session.add(route)
    session.flush()
    return route


def test_target_deleted_then_restored(client, session, docs, route0):  # noqa: F811
    before = _dump(session)
    _merge(client, docs.route1, docs.route2)
    assert _redirects_to(session, route0) == docs.route2.document_id
    entry_id = _entry(session, docs.route1).id
    assert _listed(client) == [docs.route1.document_id]

    # the merged documents are deleted with their target
    _delete(client, docs.route2)
    assert not _exists(session, docs.route1)
    assert not _exists(session, route0)
    assert _listed(client) == []
    body = _unmerge(client, entry_id, status=400).json
    assert body['errors'][0]['description'] == (
        'The target was deleted: restore it first'
    )

    _restore(client, session, docs.route2)
    assert _redirects_to(session, docs.route1) == docs.route2.document_id
    assert _listed(client) == [docs.route1.document_id]

    body = _unmerge(client, entry_id).json
    assert body['skipped'] == {}
    assert _dump(session) == before
    assert _redirects_to(session, docs.route1) is None
    assert _redirects_to(session, route0) == docs.route1.document_id


def test_source_deleted_then_restored(client, session, docs):  # noqa: F811
    before = _dump(session)
    _merge(client, docs.route1, docs.route2)
    entry_id = _entry(session, docs.route1).id

    _delete(client, docs.route1)
    assert _exists(session, docs.route2)
    assert _listed(client) == []
    body = _unmerge(client, entry_id, status=400).json
    assert body['errors'][0]['description'] == (
        'The source was deleted: restore it first'
    )

    _restore(client, session, docs.route1)
    assert _listed(client) == [docs.route1.document_id]
    _unmerge(client, entry_id)
    assert _dump(session) == before


def test_target_deleted_after_unmerge(client, session, docs, route0):  # noqa: F811
    _merge(client, docs.route1, docs.route2)
    _unmerge(client, _entry(session, docs.route1).id)

    # the old versions of route1 still redirect to route2: route1 and the
    # route merged into it stay
    assert _archives_redirecting(session, docs.route1, docs.route2) == 1
    _delete(client, docs.route2)
    assert _exists(session, docs.route1)
    assert _exists(session, route0)
    assert not _exists(session, docs.route2)
    # the old version of route1 no longer redirects (foreign key)
    assert _archives_redirecting(session, docs.route1, docs.route2) == 0

    # and the restore of route2 brings back route2 only, and the history
    _restore(client, session, docs.route2)
    assert _archives_redirecting(session, docs.route1, docs.route2) == 1
    assert _redirects_to(session, docs.route1) is None
    assert _redirects_to(session, route0) == docs.route1.document_id


def test_target_merged_again_hidden(client, session, docs, user_ids):  # noqa: F811
    create_new_version(docs.waypoint2, user_ids['contributor'])
    session.flush()
    _merge(client, docs.waypoint1, docs.waypoint2)
    _merge(client, docs.waypoint2, docs.waypoint4)
    # waypoint1 now redirects to waypoint4: only the last merge can be undone
    assert _listed(client) == [docs.waypoint2.document_id]

    _unmerge(client, _entry(session, docs.waypoint2).id)
    assert _listed(client) == [docs.waypoint1.document_id]


def test_associated_document_deleted_since(client, session, docs, user_ids):  # noqa: F811
    # an association moved by the merge, its other end deleted since: not
    # moved back (skipped); the restore of that end brings the association
    # back where it was at the deletion, with the target
    article = Article(
        categories=['site_info'],
        activities=['hiking'],
        article_type='collab',
        locales=[DocumentLocale(lang='en', title='An article')],
    )
    session.add(article)
    session.flush()
    create_new_version(article, user_ids['contributor'])
    association = Association.create(
        parent_document=docs.route1, child_document=article
    )
    session.add(association)
    session.flush()

    _merge(client, docs.route1, docs.route2)
    _delete(client, article)
    body = _unmerge(client, _entry(session, docs.route1).id).json
    assert body['skipped'] == {'associations': 1}

    _restore(client, session, article)
    assert _associated(session, docs.route2, article)
    assert not _associated(session, docs.route1, article)
