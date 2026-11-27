import datetime
from dataclasses import dataclass

import pytest

from c2corg_api.models.area import Area
from c2corg_api.models.association import Association
from c2corg_api.models.cache_version import CacheVersion
from c2corg_api.models.feed import DocumentChange, _get_participants_of_outing
from c2corg_api.models.outing import Outing
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import UserProfile
from c2corg_api.models.waypoint import WAYPOINT_TYPE, Waypoint


@dataclass
class Docs:
    """The documents of the tests, built by `docs`."""

    user1: User
    user2: User
    waypoint: Waypoint
    area1: Area
    area2: Area


@pytest.fixture
def docs(session, user_ids) -> Docs:
    user1 = session.get(User, user_ids['contributor'])
    user2 = session.get(User, user_ids['contributor2'])
    waypoint = Waypoint(waypoint_type='summit')
    session.add(waypoint)
    area1 = Area(area_type='range')
    area2 = Area(area_type='range')
    session.add_all([waypoint, area1, area2])
    session.flush()
    return Docs(user1=user1, user2=user2, waypoint=waypoint, area1=area1, area2=area2)


def test_check_user_and_area_ids_on_create_valid(session, docs):
    users_ids = [docs.user1.id, docs.user2.id]
    area_ids = [docs.area1.document_id, docs.area2.document_id]
    change = DocumentChange(
        user=docs.user1,
        change_type='created',
        document=docs.waypoint,
        document_type=WAYPOINT_TYPE,
        area_ids=area_ids,
        user_ids=users_ids,
    )
    session.add(change)
    session.flush()
    # no error, ok


def test_check_user_ids_on_create_invalid(session, docs):
    """try to create a "change" with an invalid user id"""
    users_ids = [docs.user1.id, -12345678]
    change = DocumentChange(
        user=docs.user1,
        change_type='created',
        document=docs.waypoint,
        document_type=WAYPOINT_TYPE,
        area_ids=[],
        user_ids=users_ids,
    )
    try:
        session.add(change)
        session.flush()
    except Exception as exc:
        assert 'Invalid user id: -12345678' in exc.orig.pgerror
    else:
        pytest.fail('invalid user id not detected')


def test_check_area_ids_on_create_invalid(session, docs):
    """try to create a "change" with an invalid area id"""
    area_ids = [docs.area1.document_id, -123456]
    change = DocumentChange(
        user=docs.user1,
        change_type='created',
        document=docs.waypoint,
        document_type=WAYPOINT_TYPE,
        area_ids=area_ids,
        user_ids=[],
    )
    try:
        session.add(change)
        session.flush()
    except Exception as exc:
        assert 'Invalid area id: -123456' in exc.orig.pgerror
    else:
        pytest.fail('invalid area id not detected')


def test_check_user_ids_on_update_invalid(session, docs):
    """try to update a "change" with an invalid user id"""
    # first create the change without user ids
    change = DocumentChange(
        user=docs.user1,
        change_type='created',
        document=docs.waypoint,
        document_type=WAYPOINT_TYPE,
        area_ids=[],
        user_ids=[],
    )
    session.add(change)
    session.flush()

    # then set the user ids and save
    users_ids = [docs.user1.id, -12345678]
    change.user_ids = users_ids
    try:
        session.flush()
    except Exception as exc:
        assert 'Invalid user id: -12345678' in exc.orig.pgerror
    else:
        pytest.fail('invalid user id not detected')


def test_check_changes_on_user_deletion_ok(session):
    """try to delete a user that is not referenced in a "change" """
    user = User(
        name='test',
        username='test',
        email='test@camptocamp.org',
        forum_username='test',
        moderator=True,
        password='...',
        email_validated=True,
        profile=UserProfile(categories=['amateur']),
    )
    session.add(user)
    session.flush()
    session.delete(user)
    session.flush()
    # no error, ok


def test_check_changes_on_user_deletion_error(session, docs):
    """try to delete a user that is still referenced in a "change" """
    user = User(
        name='test',
        username='test',
        email='test@camptocamp.org',
        forum_username='test',
        moderator=True,
        password='...',
        email_validated=True,
        profile=UserProfile(categories=['amateur']),
    )
    session.add(user)
    session.flush()

    participant_ids = [user.id]
    change = DocumentChange(
        user=docs.user1,
        change_type='created',
        document=docs.waypoint,
        document_type=WAYPOINT_TYPE,
        area_ids=[],
        user_ids=participant_ids,
    )
    session.add(change)
    session.flush()

    try:
        session.delete(user)
        session.flush()
    except Exception as exc:
        assert 'still references user id' in exc.orig.pgerror
    else:
        pytest.fail('user is still referenced in change')


def test_check_changes_on_area_deletion_ok(session, docs):
    """try to delete an area that is not referenced in a "change" """
    session.query(CacheVersion).filter(
        CacheVersion.document_id == docs.area1.document_id
    ).delete()
    session.delete(docs.area1)
    session.flush()
    # no error, ok


def test_check_changes_on_area_deletion_error(session, docs):
    """try to delete an area that is still referenced in a "change" """
    area_ids = [docs.area1.document_id]
    change = DocumentChange(
        user=docs.user1,
        change_type='created',
        document=docs.waypoint,
        document_type=WAYPOINT_TYPE,
        area_ids=area_ids,
        user_ids=[],
    )
    session.add(change)
    session.flush()

    try:
        session.query(CacheVersion).filter(
            CacheVersion.document_id == docs.area1.document_id
        ).delete()
        session.delete(docs.area1)
        session.flush()
    except Exception as exc:
        assert 'still references area id' in exc.orig.pgerror
    else:
        pytest.fail('area is still referenced in change')


def test_in_order(session, user_ids):
    # by user id, whatever the order of the associations (the feed
    # compares and stores them as sorted lists)
    outing = Outing(
        activities=['hiking'],
        date_start=datetime.date(2016, 2, 1),
        date_end=datetime.date(2016, 2, 1),
    )
    session.add(outing)
    session.flush()
    participant_ids = sorted([user_ids['contributor'], user_ids['contributor2']])
    for user_id in reversed(participant_ids):
        profile = session.get(User, user_id).profile
        session.add(Association.create(profile, outing))
        session.flush()

    assert _get_participants_of_outing(outing.document_id) == participant_ids
