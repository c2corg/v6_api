from dataclasses import dataclass
from datetime import date

import pytest

from c2corg_api.models.association import Association
from c2corg_api.models.outing import OUTING_TYPE, Outing
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.tests import auth_headers
from c2corg_api.views.user_partners import get_recent_partner_ids

URL = '/users/partners'


@dataclass
class Docs:
    """The outings of the tests, built by `docs`."""

    latest: Outing
    older: Outing
    oldest: Outing


def add_outing(session, day, user_ids, redirects_to=None):
    """Add an outing of the given day, with these users."""
    outing = Outing(
        activities=['skitouring'],
        date_start=day,
        date_end=day,
        redirects_to=redirects_to,
    )
    session.add(outing)
    session.flush()
    for user_id in user_ids:
        session.add(
            Association(
                parent_document_id=user_id,
                parent_document_type=USERPROFILE_TYPE,
                child_document_id=outing.document_id,
                child_document_type=OUTING_TYPE,
            )
        )
    session.flush()
    return outing


@pytest.fixture
def docs(session, user_ids) -> Docs:
    contributor = user_ids['contributor']
    contributor2 = user_ids['contributor2']
    contributor3 = user_ids['contributor3']
    moderator = user_ids['moderator']
    robot = user_ids['robot']

    latest = add_outing(
        session, date(2026, 2, 1), [contributor, contributor3, contributor2]
    )
    older = add_outing(session, date(2026, 1, 1), [contributor, contributor2])
    oldest = add_outing(session, date(2025, 6, 1), [contributor, moderator])
    # an outing without the user
    add_outing(session, date(2026, 3, 1), [contributor2, robot])
    # a merged outing, redirected to another one
    add_outing(
        session,
        date(2026, 4, 1),
        [contributor, robot],
        redirects_to=latest.document_id,
    )
    return Docs(latest=latest, older=older, oldest=oldest)


def test_unauthenticated(client):
    client.get(URL, status=403)


def test_no_outings(client, user_ids):
    response = client.get(URL, headers=auth_headers(username='contributor'))
    assert response.json == {'partners': []}


def test_partners(client, docs, user_ids):
    response = client.get(URL, headers=auth_headers(username='contributor'))

    partners = response.json['partners']
    # the partner of the latest outing first; on the same outing, the one
    # with the most outings together first
    assert [partner['document_id'] for partner in partners] == [
        user_ids['contributor2'],
        user_ids['contributor3'],
        user_ids['moderator'],
    ]
    assert partners[0]['name'] is not None
    assert 'forum_username' in partners[0]


def test_partners_of_another_user(client, docs, user_ids):
    response = client.get(URL, headers=auth_headers(username='moderator'))

    partners = response.json['partners']
    assert [partner['document_id'] for partner in partners] == [user_ids['contributor']]


def test_only_the_recent_outings(db_connection, docs, user_ids):
    partner_ids = get_recent_partner_ids(user_ids['contributor'], outings=2)
    assert partner_ids == [user_ids['contributor2'], user_ids['contributor3']]


def test_limit(db_connection, docs, user_ids):
    partner_ids = get_recent_partner_ids(user_ids['contributor'], limit=1)
    assert partner_ids == [user_ids['contributor2']]
