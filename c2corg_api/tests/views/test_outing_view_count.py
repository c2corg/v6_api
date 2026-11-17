"""The views counter of the outings: who sees it, who changes its setting."""

import importlib.util
import os
from datetime import date

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from c2corg_api.models.association import Association
from c2corg_api.models.document import Document, DocumentGeometry
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.outing import OUTING_TYPE, ArchiveOuting, Outing, OutingLocale
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.tests import alembic_scripts_folder, auth_headers, send_json
from c2corg_api.tests.views import scenarios
from c2corg_api.views.document import create_new_version

FIREFOX = 'Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0'

# the readers: anonymous, not associated to the outing, associated, moderator
ANONYMOUS = None
OTHER = 'contributor2'
USER = 'contributor'
MODERATOR = 'moderator'


def headers_of(username, **headers):
    headers.setdefault('User-Agent', FIREFOX)
    return auth_headers(username=username, headers=headers) if username else headers


@pytest.fixture
def route(session, user_ids):
    route = Route(
        activities=['skitouring'],
        elevation_max=1500,
        geometry=DocumentGeometry(geom='SRID=3857;POINT(635961 5723624)'),
        locales=[RouteLocale(lang='en', title='Mont Blanc from the air')],
    )
    session.add(route)
    session.flush()
    create_new_version(route, user_ids['contributor'])
    return route


def make_outing(session, user_ids, route, **attributes):
    """Return an outing of `contributor`, with `view_count` views."""
    view_count = attributes.pop('view_count', 0)
    outing = Outing(
        activities=['skitouring'],
        date_start=date(2016, 1, 1),
        date_end=date(2016, 1, 1),
        locales=[OutingLocale(lang='en', title='Mont Blanc', weather='sunny')],
        geometry=DocumentGeometry(geom='SRID=3857;POINT(635961 5723624)'),
        **attributes,
    )
    session.add(outing)
    session.flush()
    user_id = user_ids['contributor']
    create_new_version(outing, user_id)
    scenarios.add_association(
        session,
        Association.create(parent_document=route, child_document=outing),
        user_id=user_id,
    )
    scenarios.add_association(
        session,
        Association(
            parent_document_id=user_id,
            parent_document_type=USERPROFILE_TYPE,
            child_document_id=outing.document_id,
            child_document_type=OUTING_TYPE,
        ),
        user_id=user_id,
    )
    set_view_count(session, outing.document_id, view_count)
    return outing


def set_view_count(session, document_id, view_count):
    # as the job adding the views counted in Redis
    session.execute(
        sa.update(Document)
        .where(Document.document_id == document_id)
        .values(view_count=view_count)
    )
    session.flush()


@pytest.fixture
def outing(session, user_ids, route):
    return make_outing(session, user_ids, route, view_count=42)


@pytest.fixture
def disabled_outing(session, user_ids, route):
    return make_outing(session, user_ids, route, view_count=42, disable_view_count=True)


@pytest.fixture
def view_counter(client):
    counter = client.registry.view_counter
    counter.redis.delete(counter.key, counter.processing_key)
    yield counter
    counter.redis.delete(counter.key, counter.processing_key)


def get(client, outing, username=ANONYMOUS, query='', status=200, **headers):
    return client.get(
        f'/outings/{outing.document_id}{query}',
        headers=headers_of(username, **headers),
        status=status,
    )


def shown(client, outing, username, query=''):
    body = get(client, outing, username, query).json
    return body['view_count'], body['disable_view_count']


# Reading


@pytest.mark.parametrize(
    ('username', 'expected'),
    [
        (ANONYMOUS, (42, None)),
        (OTHER, (42, None)),
        (USER, (42, False)),
        (MODERATOR, (42, False)),
    ],
)
def test_get_enabled(client, outing, username, expected):
    # the counter is shown to everyone; its setting only to who may change it
    assert shown(client, outing, username) == expected
    assert shown(client, outing, username, '?cook=en') == expected


@pytest.mark.parametrize(
    ('username', 'expected'),
    [
        (ANONYMOUS, (None, None)),
        (OTHER, (None, None)),
        (USER, (42, True)),
        (MODERATOR, (None, True)),
    ],
)
def test_get_disabled(client, disabled_outing, username, expected):
    # only the users of the outing see a disabled counter
    assert shown(client, disabled_outing, username) == expected


@pytest.mark.parametrize(
    ('username', 'expected'),
    [(ANONYMOUS, (None, None)), (USER, (42, True)), (MODERATOR, (None, True))],
)
def test_get_edit(client, disabled_outing, username, expected):
    # the edit form gets the setting, without the cache
    assert shown(client, disabled_outing, username, '?e=1') == expected


def test_get_alternately(client, disabled_outing):
    # the cached document is completed for each reader, in any order
    for _ in range(2):
        assert shown(client, disabled_outing, USER) == (42, True)
        assert shown(client, disabled_outing, ANONYMOUS) == (None, None)


def test_view_count_not_cached(client, session, outing):
    # the views change without a new version of the outing
    assert shown(client, outing, ANONYMOUS) == (42, None)
    set_view_count(session, outing.document_id, 50)
    assert shown(client, outing, ANONYMOUS) == (50, None)


def test_etag(client, session, disabled_outing):
    anonymous = get(client, disabled_outing).headers['ETag']
    user = get(client, disabled_outing, USER).headers['ETag']
    assert anonymous != user

    # same reader, same answer: not modified
    get(client, disabled_outing, USER, status=304, **{'If-None-Match': user})
    get(client, disabled_outing, status=304, **{'If-None-Match': anonymous})

    # the answer to another reader is not the one of this reader
    body = get(client, disabled_outing, USER, **{'If-None-Match': anonymous}).json
    assert body['view_count'] == 42

    # nor is the answer of before the views were added
    set_view_count(session, disabled_outing.document_id, 43)
    body = get(client, disabled_outing, USER, **{'If-None-Match': user}).json
    assert body['view_count'] == 43


def test_cache_headers(client, outing):
    response = get(client, outing)
    assert response.headers['Vary'] == 'Authorization'
    assert 'Cache-Control' not in response.headers

    response = get(client, outing, USER)
    assert response.headers['Vary'] == 'Authorization'
    assert response.headers['Cache-Control'] == 'private'


def test_get_redirected(client, session, outing, disabled_outing):
    disabled_outing.redirects_to = outing.document_id
    session.flush()
    body = get(client, disabled_outing, USER).json
    assert body['redirects_to'] == outing.document_id
    assert 'view_count' not in body


def test_collection(client, outing, disabled_outing):
    for username in (ANONYMOUS, USER, MODERATOR):
        body = client.get('/outings', headers=headers_of(username)).json
        ids = {doc['document_id'] for doc in body['documents']}
        assert {outing.document_id, disabled_outing.document_id} <= ids
        for doc in body['documents']:
            assert 'view_count' not in doc
            assert 'disable_view_count' not in doc


def test_other_documents(client, route):
    # only the outings get the counter
    body = client.get(f'/routes/{route.document_id}').json
    assert 'view_count' not in body
    assert 'disable_view_count' not in body


# Counting


def counted(counter, document_id):
    value = counter.redis.hget(counter.key, document_id)
    return int(value) if value is not None else 0


def test_disabled_counter_still_counts(client, view_counter, disabled_outing):
    # disabling the counter hides it, its users still see the views
    get(client, disabled_outing)
    get(client, disabled_outing, OTHER)
    assert counted(view_counter, disabled_outing.document_id) == 2


# Writing


def put_body(outing, route, user_ids, **attributes):
    locale = outing.locales[0]
    document = {
        'document_id': outing.document_id,
        'version': outing.version,
        'activities': ['skitouring'],
        'date_start': '2016-01-01',
        'date_end': '2016-01-01',
        'locales': [
            {
                'lang': 'en',
                'title': locale.title,
                'weather': locale.weather,
                'version': locale.version,
            }
        ],
        'associations': {
            'users': [{'document_id': user_ids['contributor']}],
            'routes': [{'document_id': route.document_id}],
        },
    }
    document.update(attributes)
    return {'message': 'Update', 'document': document}


def put(client, outing, body, username, status=200):
    send_json(
        client,
        'put',
        f'/outings/{outing.document_id}',
        body,
        headers=headers_of(username),
        status=status,
    )


def stored(session, outing):
    session.expire_all()
    return session.get(Outing, outing.document_id)


def test_put_disable(client, session, user_ids, route, outing):
    version = outing.version
    body = put_body(outing, route, user_ids, disable_view_count=True)
    put(client, outing, body, USER)
    current = stored(session, outing)
    assert current.disable_view_count is True
    # versioned, as the other attributes
    assert current.version == version + 1
    archive = (
        session.query(ArchiveOuting)
        .filter(ArchiveOuting.document_id == outing.document_id)
        .filter(ArchiveOuting.version == current.version)
        .one()
    )
    assert archive.disable_view_count is True
    assert shown(client, outing, ANONYMOUS) == (None, None)
    assert shown(client, outing, USER) == (42, True)


def test_put_enable(client, session, user_ids, route, disabled_outing):
    body = put_body(disabled_outing, route, user_ids, disable_view_count=False)
    put(client, disabled_outing, body, USER)
    assert stored(session, disabled_outing).disable_view_count is False
    assert shown(client, disabled_outing, ANONYMOUS) == (42, None)


@pytest.mark.parametrize('username', [USER, MODERATOR])
@pytest.mark.parametrize('given', [{}, {'disable_view_count': None}])
def test_put_without_setting(
    client, session, user_ids, route, disabled_outing, username, given
):
    # a client which did not get the setting (or sends null) does not change it
    body = put_body(disabled_outing, route, user_ids, elevation_max=1600, **given)
    put(client, disabled_outing, body, username)
    current = stored(session, disabled_outing)
    assert current.elevation_max == 1600
    assert current.disable_view_count is True


def test_put_unchanged_setting_no_version(
    client, session, user_ids, route, disabled_outing
):
    # saving the outing as it is does not make a new version
    versions = session.query(DocumentVersion).filter_by(
        document_id=disabled_outing.document_id
    )
    count = versions.count()
    version = disabled_outing.version
    body = put_body(disabled_outing, route, user_ids, disable_view_count=True)
    put(client, disabled_outing, body, USER)
    assert stored(session, disabled_outing).version == version
    assert versions.count() == count


def test_put_moderator(client, session, user_ids, route, disabled_outing):
    # as for the other attributes of an outing, a moderator may change it
    body = put_body(disabled_outing, route, user_ids, disable_view_count=False)
    put(client, disabled_outing, body, MODERATOR)
    assert stored(session, disabled_outing).disable_view_count is False


def test_put_other_user(client, session, user_ids, route, outing):
    body = put_body(outing, route, user_ids, disable_view_count=True)
    put(client, outing, body, OTHER, status=403)
    assert stored(session, outing).disable_view_count is False


def test_put_view_count_ignored(client, session, user_ids, route, outing):
    body = put_body(outing, route, user_ids, view_count=1000, elevation_max=1600)
    put(client, outing, body, USER)
    current = stored(session, outing)
    assert current.elevation_max == 1600
    assert current.view_count == 42


def post_body(route, user_ids, **attributes):
    body = {
        'activities': ['skitouring'],
        'date_start': '2016-01-01',
        'date_end': '2016-01-01',
        'locales': [{'lang': 'en', 'title': 'Some nice loop'}],
        'associations': {
            'users': [{'document_id': user_ids['contributor']}],
            'routes': [{'document_id': route.document_id}],
        },
    }
    body.update(attributes)
    return body


def post(client, session, body):
    response = send_json(
        client, 'post', '/outings', body, headers=headers_of(USER), status=200
    )
    session.expire_all()
    return session.get(Outing, response.json['document_id'])


@pytest.mark.parametrize(
    ('given', 'expected'),
    [
        ({}, False),
        ({'disable_view_count': None}, False),
        ({'disable_view_count': False}, False),
        ({'disable_view_count': True}, True),
    ],
)
def test_post(client, session, user_ids, route, given, expected):
    outing = post(client, session, post_body(route, user_ids, **given))
    assert outing.disable_view_count is expected
    assert outing.versions[0].document_archive.disable_view_count is expected


def test_post_view_count_ignored(client, session, user_ids, route):
    outing = post(client, session, post_body(route, user_ids, view_count=1000))
    assert outing.view_count == 0


# Migration


def load_migration():
    path = os.path.join(
        alembic_scripts_folder,
        'versions',
        'abae46fab037_add_disable_view_count_to_outings.py',
    )
    spec = importlib.util.spec_from_file_location('migration_abae46fab037', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def columns(connection, table):
    return {
        column['name']: column
        for column in sa.inspect(connection).get_columns(table, schema='guidebook')
    }


def test_migration(db_connection, outing):
    # in the transaction of the test: rolled back after it
    migration = load_migration()
    assert migration.down_revision == '2d710311ac56'
    with Operations.context(MigrationContext.configure(db_connection)):
        migration.downgrade()
        for table in ('outings', 'outings_archives'):
            assert 'disable_view_count' not in columns(db_connection, table)

        migration.upgrade()
        for table in ('outings', 'outings_archives'):
            column = columns(db_connection, table)['disable_view_count']
            assert not column['nullable']
            # the counter of the existing outings is enabled
            values = db_connection.execute(
                sa.select(sa.column('disable_view_count'))
                .distinct()
                .select_from(sa.table(table, schema='guidebook'))
            ).scalars()
            assert set(values) == {False}
