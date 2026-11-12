import datetime
from dataclasses import dataclass

import pytest

from c2corg_api.models.document import DocumentGeometry
from c2corg_api.models.document_history import DocumentVersion, HistoryMetaData
from c2corg_api.models.outing import Outing
from c2corg_api.models.route import Route, RouteLocale
from c2corg_api.models.user_profile import UserProfile
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.tests import invalid_parameters
from c2corg_api.tests.views.test_feed import get_document_ids
from c2corg_api.views.document import create_new_version

PREFIX = '/documents/changes'


@dataclass
class Docs:
    """The documents of the tests, built by `docs`."""

    waypoint1: Waypoint
    waypoint2: Waypoint
    waypoint3: Waypoint
    route1: Route
    outing: Outing
    profile2: UserProfile


@pytest.fixture(autouse=True)
def docs(session, user_ids) -> Docs:
    contributor_id = user_ids['contributor']

    waypoint1 = Waypoint(
        waypoint_type='summit',
        elevation=2000,
        geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
        locales=[
            WaypointLocale(
                lang='fr',
                title='Dent de Crolles',
                description='...',
                summary='La Dent de Crolles',
            )
        ],
    )
    session.add(waypoint1)
    session.flush()
    create_new_version(waypoint1, contributor_id)
    session.flush()

    waypoint2 = Waypoint(
        waypoint_type='summit',
        elevation=4985,
        geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
        locales=[
            WaypointLocale(
                lang='en',
                title='Mont Blanc',
                description='...',
                summary='The heighest point in Europe',
            )
        ],
    )
    session.add(waypoint2)
    session.flush()
    create_new_version(waypoint2, contributor_id)
    session.flush()

    waypoint3 = Waypoint(
        waypoint_type='summit',
        elevation=4985,
        geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
        locales=[
            WaypointLocale(
                lang='en',
                title='Mont Blanc',
                description='...',
                summary='The heighest point in Europe',
            )
        ],
    )
    session.add(waypoint3)
    session.flush()
    create_new_version(waypoint3, contributor_id)
    session.flush()

    route1 = Route(
        activities=['skitouring'],
        elevation_max=1500,
        elevation_min=700,
        main_waypoint_id=waypoint1.document_id,
        locales=[
            RouteLocale(
                lang='fr',
                title='Mont Blanc du ciel',
                description='...',
                summary='Ski',
            )
        ],
    )
    session.add(route1)
    session.flush()
    create_new_version(route1, contributor_id)
    session.flush()

    outing = Outing(
        activities=['skitouring'],
        date_start=datetime.date(2016, 1, 1),
        date_end=datetime.date(2016, 1, 1),
        elevation_max=1500,
        elevation_min=700,
        height_diff_up=800,
        height_diff_down=800,
    )
    session.add(outing)
    session.flush()
    create_new_version(outing, contributor_id)
    session.flush()

    profile2 = UserProfile(categories=['amateur'])
    session.add(profile2)
    session.flush()
    return Docs(
        waypoint1=waypoint1,
        waypoint2=waypoint2,
        waypoint3=waypoint3,
        route1=route1,
        outing=outing,
        profile2=profile2,
    )


def test_counts(session):
    # besides these documents, the profiles of the global test users have
    # a version per locale (7, the contributor has two) and a history
    # entry each (6)
    version_count = session.query(DocumentVersion).count()
    assert 4 + 7 == version_count

    hist_meta_count = session.query(HistoryMetaData).count()
    assert 5 + 6 == hist_meta_count


def test_get_changes(client, docs):
    response = client.get(PREFIX, status=200)
    body = response.json

    assert 'total' not in body
    assert 'pagination_token' in body
    assert 'feed' in body

    feed = body['feed']
    assert 4 == len(feed)

    for doc in feed:
        assert doc['document']['type'] != 'o'
        assert doc['document']['type'] != 'u'

    # check that the change for the route (latest change) is listed first
    latest_change = feed[0]

    assert docs.route1.document_id == latest_change['document']['document_id']


def test_get_changes_empty(client):
    response = client.get(PREFIX + '?token=0', status=200)
    body = response.json

    assert 'pagination_token' not in body
    assert 'feed' in body

    feed = body['feed']
    assert 0 == len(feed)


def test_get_changes_paginated(client, docs):
    response = client.get(PREFIX + '?limit=2', status=200)
    body = response.json

    document_ids = get_document_ids(body)
    assert 2 == len(document_ids)
    assert document_ids == [docs.route1.document_id, docs.waypoint3.document_id]
    pagination_token = body['pagination_token']

    # last 2 changes
    response = client.get(PREFIX + '?limit=2&token=' + pagination_token, status=200)
    body = response.json

    document_ids = get_document_ids(body)
    assert 2 == len(document_ids)
    assert document_ids == [docs.waypoint2.document_id, docs.waypoint1.document_id]
    pagination_token = body['pagination_token']

    # empty response
    response = client.get(PREFIX + '?limit=2&token=' + pagination_token, status=200)
    body = response.json

    feed = body['feed']
    assert 0 == len(feed)


def test_get_changes_pagination_invalid_format(client):
    response = client.get(PREFIX + '?token=invalid-token', status=422)
    assert ('query', 'token', 'invalid format') in invalid_parameters(response)


def test_get_changes_userid_invalid_format(client):
    response = client.get(PREFIX + '?u=invalid-user_id', status=422)
    assert ('query', 'u', 'invalid u') in invalid_parameters(response)
