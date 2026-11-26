import datetime
import json
from collections import Counter

from httmock import HTTMock, all_requests
from sqlalchemy import Text, cast, select
from sqlalchemy.sql.expression import literal_column
from sqlalchemy.sql.functions import func

from c2corg_api.models.association import Association, AssociationLog
from c2corg_api.models.deleted_document import RETENTION
from c2corg_api.models.document import Document
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
    assert session.get(
        Association, (docs.waypoint2.document_id, docs.route1.document_id)
    )
    assert not session.get(
        Association, (docs.waypoint1.document_id, docs.route1.document_id)
    )
    assert session.get(
        Association, (docs.waypoint1.document_id, docs.route2.document_id)
    )


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
    client.get('/documents/merged', status=403)


def test_list(client, session, docs):  # noqa: F811
    _merge(client, docs.route1, docs.route2)
    body = client.get('/documents/merged', headers=_moderator(), status=200).json
    assert body['total'] == 1
    (merge,) = body['merges']
    assert merge['source_document_id'] == docs.route1.document_id
    assert merge['target_document_id'] == docs.route2.document_id
    assert merge['title'] == 'Mont Blanc du ciel'
    assert merge['merged_by']['name'] == 'Moderator'
    assert merge['counts']['favourites_moved'] == 1

    _unmerge(client, merge['id'])
    body = client.get('/documents/merged', headers=_moderator(), status=200).json
    assert body['total'] == 0
