import pytest

from c2corg_api.models.document import DocumentGeometry, UpdateType
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.views.document import create_new_version, update_version


@pytest.fixture
def waypoint(session, user_ids):
    """Return a waypoint created by a contributor, then edited by a moderator."""
    waypoint = Waypoint(
        waypoint_type='summit',
        elevation=2000,
        geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
        locales=[WaypointLocale(lang='en', title='Mont Granier')],
    )
    session.add(waypoint)
    session.flush()
    create_new_version(waypoint, user_ids['contributor'])
    waypoint.elevation = 2001
    session.flush()
    update_version(
        waypoint, user_ids['moderator'], 'elevation', [UpdateType.FIGURES], []
    )
    session.flush()
    return waypoint


def test_history_marks_the_moderators(client, user_ids, waypoint):
    url = f'/document/{waypoint.document_id}/history/en'

    versions = client.get(url, status=200).json['versions']

    assert [(v['user_id'], v['moderator']) for v in versions] == [
        (user_ids['contributor'], False),
        (user_ids['moderator'], True),
    ]


def test_version_marks_the_moderators(client, session, user_ids, waypoint):
    version_ids = [
        version_id
        for (version_id,) in session.query(DocumentVersion.id)
        .filter(DocumentVersion.document_id == waypoint.document_id)
        .order_by(DocumentVersion.id)
    ]

    for version_id, moderator in zip(version_ids, [False, True], strict=True):
        url = f'/waypoints/{waypoint.document_id}/en/{version_id}'
        version = client.get(url, status=200).json['version']
        assert version['moderator'] is moderator
