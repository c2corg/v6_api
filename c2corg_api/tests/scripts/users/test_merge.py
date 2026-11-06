import datetime
from dataclasses import dataclass

import pytest
from sqlalchemy.sql.expression import any_, exists, or_

from c2corg_api.models.area import Area
from c2corg_api.models.area_association import AreaAssociation
from c2corg_api.models.association import Association, AssociationLog
from c2corg_api.models.document import (
    ArchiveDocument,
    ArchiveDocumentGeometry,
    ArchiveDocumentLocale,
    Document,
    DocumentGeometry,
    DocumentLocale,
)
from c2corg_api.models.document_history import HistoryMetaData
from c2corg_api.models.document_tag import DocumentTag, DocumentTagLog
from c2corg_api.models.feed import DocumentChange, update_feed_document_create
from c2corg_api.models.mailinglist import Mailinglist
from c2corg_api.models.outing import OUTING_TYPE, Outing, OutingLocale
from c2corg_api.models.route import ROUTE_TYPE, Route, RouteLocale
from c2corg_api.models.sso import SsoExternalId
from c2corg_api.models.token import Token
from c2corg_api.models.topo_map import TopoMap
from c2corg_api.models.topo_map_association import TopoMapAssociation
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import (
    USERPROFILE_TYPE,
    ArchiveUserProfile,
    UserProfile,
)
from c2corg_api.models.waypoint import Waypoint, WaypointLocale
from c2corg_api.scripts.users.merge import merge_user_accounts
from c2corg_api.views.document import create_new_version


@dataclass
class Docs:
    """The documents of the tests, built by `docs`."""

    contributor: object
    contributor2: object
    map1: TopoMap
    waypoint1: Waypoint
    route1: Route
    outing1: Outing
    outing2: Outing


@pytest.fixture
def docs(session, user_ids) -> Docs:
    contributor = session.get(User, user_ids['contributor'])
    contributor2 = session.get(User, user_ids['contributor2'])

    ml = Mailinglist(
        listname='avalanche',
        user_id=contributor.id,
        email=contributor.email,
    )
    session.add(ml)

    area = Area(
        area_type='range',
        locales=[DocumentLocale(lang='fr', title='Chartreuse')],
        geometry=DocumentGeometry(
            geom_detail='SRID=3857;POLYGON((668518.249382151 5728802.39591739,668518.249382151 5745465.66808356,689156.247019149 5745465.66808356,689156.247019149 5728802.39591739,668518.249382151 5728802.39591739))'  # noqa
        ),
    )
    session.add(area)
    session.add(AreaAssociation(document=contributor.profile, area=area))
    session.flush()

    map1 = TopoMap(
        code='3232ET',
        editor='IGN',
        scale='25000',
        locales=[DocumentLocale(lang='fr', title='Belley')],
        geometry=DocumentGeometry(
            geom_detail='SRID=3857;POLYGON((611774.917032556 5706934.10657514,611774.917032556 5744215.5846397,642834.402570357 5744215.5846397,642834.402570357 5706934.10657514,611774.917032556 5706934.10657514))'  # noqa: E501
        ),
    )
    session.add(map1)
    session.flush()
    session.add(TopoMapAssociation(document=contributor.profile, topo_map=map1))
    session.flush()

    waypoint1 = Waypoint(
        waypoint_type='summit',
        elevation=2203,
        locales=[WaypointLocale(lang='en', title='Mont Granier')],
        geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
    )
    session.add(waypoint1)
    session.flush()
    create_new_version(waypoint1, contributor.id)
    update_feed_document_create(waypoint1, contributor.id)

    route1_geometry = DocumentGeometry(
        geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723644)',
        geom='SRID=3857;POINT(635961 5723624)',
    )
    route1 = Route(activities=['skitouring'], geometry=route1_geometry)
    route1.locales.append(
        RouteLocale(
            lang='en',
            title='Mont Blanc from the air',
            description='...',
            title_prefix='Mont Blanc :',
            gear='paraglider',
        )
    )
    session.add(route1)
    session.flush()
    create_new_version(route1, contributor.id)
    update_feed_document_create(route1, contributor.id)
    session.add(Association.create(parent_document=waypoint1, child_document=route1))

    outing1 = Outing(
        activities=['skitouring'],
        date_start=datetime.date(2016, 1, 1),
        date_end=datetime.date(2016, 1, 1),
        elevation_max=1500,
        locales=[OutingLocale(lang='en', title='foo')],
        geometry=DocumentGeometry(
            geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723644)'
        ),
    )
    session.add(outing1)
    session.flush()
    create_new_version(outing1, contributor.id)
    update_feed_document_create(outing1, contributor.id)

    outing2 = Outing(
        activities=['skitouring'],
        date_start=datetime.date(2016, 1, 1),
        date_end=datetime.date(2016, 1, 1),
        elevation_max=1500,
        locales=[OutingLocale(lang='en', title='foo')],
        geometry=DocumentGeometry(
            geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723644)'
        ),
    )
    session.add(outing2)
    session.flush()
    create_new_version(outing2, contributor.id)
    update_feed_document_create(outing2, contributor.id)

    session.add(
        Association(
            parent_document_id=contributor.id,
            parent_document_type=USERPROFILE_TYPE,
            child_document_id=outing1.document_id,
            child_document_type=OUTING_TYPE,
        )
    )
    session.add(
        Association(
            parent_document_id=contributor.id,
            parent_document_type=USERPROFILE_TYPE,
            child_document_id=outing2.document_id,
            child_document_type=OUTING_TYPE,
        )
    )
    session.add(
        Association(
            parent_document_id=contributor2.id,
            parent_document_type=USERPROFILE_TYPE,
            child_document_id=outing2.document_id,
            child_document_type=OUTING_TYPE,
        )
    )

    session.add(
        DocumentTag(
            document_id=route1.document_id,
            document_type=ROUTE_TYPE,
            user_id=contributor.id,
        )
    )
    session.add(
        DocumentTagLog(
            document_id=route1.document_id,
            document_type=ROUTE_TYPE,
            user_id=contributor.id,
            is_creation=True,
        )
    )

    session.flush()
    return Docs(
        contributor=contributor,
        contributor2=contributor2,
        map1=map1,
        waypoint1=waypoint1,
        route1=route1,
        outing1=outing1,
        outing2=outing2,
    )


def test_merge_user_accounts(session, user_ids, queue_config, docs):
    source_id = user_ids['contributor']
    target_id = user_ids['contributor2']

    # Check data before merging
    assert _count_area_associations(session, source_id) == 1

    assert _count_associations(session, source_id) == 2
    assert _count_associations(session, target_id) == 1

    assert _count_feed_entries(session, source_id) == 4
    assert _count_feed_entries(session, target_id) == 0
    assert _count_associated_feed_entries(session, source_id) == 4
    assert _count_associated_feed_entries(session, target_id) == 0

    assert _count_metadata_entries(session, source_id) == 5
    # the target has the history entry of its own profile
    assert _count_metadata_entries(session, target_id) == 1

    assert _is_registered_to_ml(session, docs.contributor)
    assert not _is_registered_to_ml(session, docs.contributor2)

    assert 1 == _count_tags(session, source_id)
    assert 1 == _count_tag_logs(session, source_id)
    assert 0 == _count_tags(session, target_id)
    assert 0 == _count_tag_logs(session, target_id)

    # Actually do the merge
    merge_user_accounts(source_id, target_id, queue_config)

    # Check data after merging
    assert _count_area_associations(session, source_id) == 0

    assert _count_associations(session, source_id) == 0
    assert _count_associations(session, target_id) == 2
    assert _count_association_logs(session, source_id) == 0

    assert _count_feed_entries(session, source_id) == 0
    assert _count_feed_entries(session, target_id) == 4
    assert _count_associated_feed_entries(session, source_id) == 0
    assert _count_associated_feed_entries(session, target_id) == 4

    assert _count_metadata_entries(session, source_id) == 0
    assert _count_metadata_entries(session, target_id) == 4 + 1

    assert not _is_registered_to_ml(session, docs.contributor)
    assert not _is_registered_to_ml(session, docs.contributor2)

    # Check that the profile document and archives have been deleted
    count = (
        session.query(UserProfile).filter(UserProfile.document_id == source_id).count()
    )
    assert 0 == count
    count = session.query(Document).filter(Document.document_id == source_id).count()
    assert 0 == count
    count = (
        session.query(DocumentLocale)
        .filter(DocumentLocale.document_id == source_id)
        .count()
    )
    assert 0 == count
    count = (
        session.query(DocumentGeometry)
        .filter(DocumentGeometry.document_id == source_id)
        .count()
    )
    assert 0 == count

    # Check the archives have been cleared too
    count = (
        session.query(ArchiveUserProfile)
        .filter(ArchiveUserProfile.document_id == source_id)
        .count()
    )
    assert 0 == count
    count = (
        session.query(ArchiveDocument)
        .filter(ArchiveDocument.document_id == source_id)
        .count()
    )
    assert 0 == count
    count = (
        session.query(ArchiveDocumentLocale)
        .filter(ArchiveDocumentLocale.document_id == source_id)
        .count()
    )
    assert 0 == count
    count = (
        session.query(ArchiveDocumentGeometry)
        .filter(ArchiveDocumentGeometry.document_id == source_id)
        .count()
    )
    assert 0 == count

    # Check that user account has been removed
    count = session.query(User).filter(User.id == source_id).count()
    assert 0 == count
    count = session.query(Token).filter(Token.userid == source_id).count()
    count = (
        session.query(SsoExternalId).filter(SsoExternalId.user_id == source_id).count()
    )
    assert 0 == count

    # Check tags have been transfered to the target user
    assert 0 == _count_tags(session, source_id)
    assert 0 == _count_tag_logs(session, source_id)
    assert 1 == _count_tags(session, target_id)
    assert 1 == _count_tag_logs(session, target_id)


def _count_tags(session, user_id):
    return session.query(DocumentTag).filter(DocumentTag.user_id == user_id).count()


def _count_tag_logs(session, user_id):
    return (
        session.query(DocumentTagLog).filter(DocumentTagLog.user_id == user_id).count()
    )


def _count_area_associations(session, user_id):
    return (
        session.query(AreaAssociation)
        .filter(AreaAssociation.document_id == user_id)
        .count()
    )


def _count_associations(session, user_id):
    return (
        session.query(Association)
        .filter(
            or_(
                Association.parent_document_id == user_id,
                Association.child_document_id == user_id,
            )
        )
        .count()
    )


def _count_association_logs(session, user_id):
    return (
        session.query(AssociationLog)
        .filter(
            or_(
                AssociationLog.parent_document_id == user_id,
                AssociationLog.child_document_id == user_id,
                AssociationLog.user_id == user_id,
            )
        )
        .count()
    )


def _count_feed_entries(session, user_id):
    return (
        session.query(DocumentChange).filter(DocumentChange.user_id == user_id).count()
    )


def _count_associated_feed_entries(session, user_id):
    return (
        session.query(DocumentChange)
        .filter(any_(DocumentChange.user_ids) == user_id)
        .count()
    )


def _count_metadata_entries(session, user_id):
    return (
        session.query(HistoryMetaData)
        .filter(HistoryMetaData.user_id == user_id)
        .count()
    )


def _is_registered_to_ml(session, user):
    return session.query(exists().where(Mailinglist.email == user.email)).scalar()
