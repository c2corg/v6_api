from datetime import date

from sqlalchemy import any_, exists, or_

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
from c2corg_api.tests import BaseTestCase, global_userids
from c2corg_api.routers.helpers.document_crud import create_new_version, update_version


class MergeUsersTest(BaseTestCase):
    def setUp(self):  # noqa
        BaseTestCase.setUp(self)
        self._add_test_data()

    def test_merge_user_accounts(self):
        source_id = global_userids['contributor']
        target_id = global_userids['contributor2']

        # Check data before merging
        assert self._count_area_associations(source_id) == 1

        assert self._count_associations(source_id) == 2
        assert self._count_associations(target_id) == 1

        assert self._count_feed_entries(source_id) == 4
        assert self._count_feed_entries(target_id) == 0
        assert self._count_associated_feed_entries(source_id) == 4
        assert self._count_associated_feed_entries(target_id) == 0

        assert self._count_metadata_entries(source_id) == 5
        assert self._count_metadata_entries(target_id) == 0

        assert self._is_registered_to_ml(self.contributor)
        assert not self._is_registered_to_ml(self.contributor2)

        assert 1 == self._count_tags(source_id)
        assert 1 == self._count_tag_logs(source_id)
        assert 0 == self._count_tags(target_id)
        assert 0 == self._count_tag_logs(target_id)

        # Actually do the merge
        merge_user_accounts(source_id, target_id, self.queue_config)

        # Check data after merging
        assert self._count_area_associations(source_id) == 0

        assert self._count_associations(source_id) == 0
        assert self._count_associations(target_id) == 2
        assert self._count_association_logs(source_id) == 0

        assert self._count_feed_entries(source_id) == 0
        assert self._count_feed_entries(target_id) == 4
        assert self._count_associated_feed_entries(source_id) == 0
        assert self._count_associated_feed_entries(target_id) == 4

        assert self._count_metadata_entries(source_id) == 0
        assert self._count_metadata_entries(target_id) == 4

        assert not self._is_registered_to_ml(self.contributor)
        assert not self._is_registered_to_ml(self.contributor2)

        # Check that the profile document and archives have been deleted
        count = (
            self.session.query(UserProfile)
            .filter(UserProfile.document_id == source_id)
            .count()
        )
        assert 0 == count
        count = (
            self.session.query(Document)
            .filter(Document.document_id == source_id)
            .count()
        )
        assert 0 == count
        count = (
            self.session.query(DocumentLocale)
            .filter(DocumentLocale.document_id == source_id)
            .count()
        )
        assert 0 == count
        count = (
            self.session.query(DocumentGeometry)
            .filter(DocumentGeometry.document_id == source_id)
            .count()
        )
        assert 0 == count

        # Check the archives have been cleared too
        count = (
            self.session.query(ArchiveUserProfile)
            .filter(ArchiveUserProfile.document_id == source_id)
            .count()
        )
        assert 0 == count
        count = (
            self.session.query(ArchiveDocument)
            .filter(ArchiveDocument.document_id == source_id)
            .count()
        )
        assert 0 == count
        count = (
            self.session.query(ArchiveDocumentLocale)
            .filter(ArchiveDocumentLocale.document_id == source_id)
            .count()
        )
        assert 0 == count
        count = (
            self.session.query(ArchiveDocumentGeometry)
            .filter(ArchiveDocumentGeometry.document_id == source_id)
            .count()
        )
        assert 0 == count

        # Check that user account has been removed
        count = self.session.query(User).filter(User.id == source_id).count()
        assert 0 == count
        count = self.session.query(Token).filter(Token.userid == source_id).count()
        count = (
            self.session.query(SsoExternalId)
            .filter(SsoExternalId.user_id == source_id)
            .count()
        )
        assert 0 == count

        # Check tags have been transfered to the target user
        assert 0 == self._count_tags(source_id)
        assert 0 == self._count_tag_logs(source_id)
        assert 1 == self._count_tags(target_id)
        assert 1 == self._count_tag_logs(target_id)

    def _count_tags(self, user_id):
        return (
            self.session.query(DocumentTag)
            .filter(DocumentTag.user_id == user_id)
            .count()
        )

    def _count_tag_logs(self, user_id):
        return (
            self.session.query(DocumentTagLog)
            .filter(DocumentTagLog.user_id == user_id)
            .count()
        )

    def _count_area_associations(self, user_id):
        return (
            self.session.query(AreaAssociation)
            .filter(AreaAssociation.document_id == user_id)
            .count()
        )

    def _count_associations(self, user_id):
        return (
            self.session.query(Association)
            .filter(
                or_(
                    Association.parent_document_id == user_id,
                    Association.child_document_id == user_id,
                )
            )
            .count()
        )

    def _count_association_logs(self, user_id):
        return (
            self.session.query(AssociationLog)
            .filter(
                or_(
                    AssociationLog.parent_document_id == user_id,
                    AssociationLog.child_document_id == user_id,
                    AssociationLog.user_id == user_id,
                )
            )
            .count()
        )

    def _count_feed_entries(self, user_id):
        return (
            self.session.query(DocumentChange)
            .filter(DocumentChange.user_id == user_id)
            .count()
        )

    def _count_associated_feed_entries(self, user_id):
        return (
            self.session.query(DocumentChange)
            .filter(any_(DocumentChange.user_ids) == user_id)
            .count()
        )

    def _count_metadata_entries(self, user_id):
        return (
            self.session.query(HistoryMetaData)
            .filter(HistoryMetaData.user_id == user_id)
            .count()
        )

    def _is_registered_to_ml(self, user):
        return self.session.query(
            exists().where(Mailinglist.email == user.email)
        ).scalar()

    def _add_test_data(self):
        self.contributor = self.session.get(User, global_userids['contributor'])
        self.contributor2 = self.session.get(User, global_userids['contributor2'])

        create_new_version(self.contributor.profile, self.contributor.id)

        ml = Mailinglist(
            listname='avalanche',
            user_id=self.contributor.id,
            email=self.contributor.email,
        )
        self.session.add(ml)

        area = Area(
            area_type='range',
            locales=[DocumentLocale(lang='fr', title='Chartreuse')],
            geometry=DocumentGeometry(
                geom_detail='SRID=3857;POLYGON((668518.249382151 5728802.39591739,668518.249382151 5745465.66808356,689156.247019149 5745465.66808356,689156.247019149 5728802.39591739,668518.249382151 5728802.39591739))'  # noqa
            ),
        )
        self.session.add(area)
        self.session.add(AreaAssociation(document=self.contributor.profile, area=area))
        self.session.flush()

        self.map1 = TopoMap(
            code='3232ET',
            editor='IGN',
            scale='25000',
            locales=[DocumentLocale(lang='fr', title='Belley')],
            geometry=DocumentGeometry(
                geom_detail='SRID=3857;POLYGON((611774.917032556 5706934.10657514,611774.917032556 5744215.5846397,642834.402570357 5744215.5846397,642834.402570357 5706934.10657514,611774.917032556 5706934.10657514))'  # noqa: E501
            ),
        )
        self.session.add(self.map1)
        self.session.flush()
        self.session.add(
            TopoMapAssociation(document=self.contributor.profile, topo_map=self.map1)
        )
        self.session.flush()

        self.waypoint1 = Waypoint(
            waypoint_type='summit',
            elevation=2203,
            locales=[WaypointLocale(lang='en', title='Mont Granier')],
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
        )
        self.session.add(self.waypoint1)
        self.session.flush()
        create_new_version(self.waypoint1, self.contributor.id)
        update_feed_document_create(self.waypoint1, self.contributor.id)

        route1_geometry = DocumentGeometry(
            geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723644)',
            geom='SRID=3857;POINT(635961 5723624)',
        )
        self.route1 = Route(activities=['skitouring'], geometry=route1_geometry)
        self.route1.locales.append(
            RouteLocale(
                lang='en',
                title='Mont Blanc from the air',
                description='...',
                title_prefix='Mont Blanc :',
                gear='paraglider',
            )
        )
        self.session.add(self.route1)
        self.session.flush()
        create_new_version(self.route1, self.contributor.id)
        update_feed_document_create(self.route1, self.contributor.id)
        self.session.add(
            Association.create(
                parent_document=self.waypoint1, child_document=self.route1
            )
        )

        self.outing1 = Outing(
            activities=['skitouring'],
            date_start=date(2016, 1, 1),
            date_end=date(2016, 1, 1),
            elevation_max=1500,
            locales=[OutingLocale(lang='en', title='foo')],
            geometry=DocumentGeometry(
                geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723644)'  # noqa
            ),
        )
        self.session.add(self.outing1)
        self.session.flush()
        create_new_version(self.outing1, self.contributor.id)
        update_feed_document_create(self.outing1, self.contributor.id)

        self.outing2 = Outing(
            activities=['skitouring'],
            date_start=date(2016, 1, 1),
            date_end=date(2016, 1, 1),
            elevation_max=1500,
            locales=[OutingLocale(lang='en', title='foo')],
            geometry=DocumentGeometry(
                geom_detail='SRID=3857;LINESTRING(635956 5723604, 635966 5723644)'  # noqa
            ),
        )
        self.session.add(self.outing2)
        self.session.flush()
        create_new_version(self.outing2, self.contributor.id)
        update_feed_document_create(self.outing2, self.contributor.id)

        self.session.add(
            Association(
                parent_document_id=self.contributor.id,
                parent_document_type=USERPROFILE_TYPE,
                child_document_id=self.outing1.document_id,
                child_document_type=OUTING_TYPE,
            )
        )
        self.session.add(
            Association(
                parent_document_id=self.contributor.id,
                parent_document_type=USERPROFILE_TYPE,
                child_document_id=self.outing2.document_id,
                child_document_type=OUTING_TYPE,
            )
        )
        self.session.add(
            Association(
                parent_document_id=self.contributor2.id,
                parent_document_type=USERPROFILE_TYPE,
                child_document_id=self.outing2.document_id,
                child_document_type=OUTING_TYPE,
            )
        )

        self.session.add(
            DocumentTag(
                document_id=self.route1.document_id,
                document_type=ROUTE_TYPE,
                user_id=self.contributor.id,
            )
        )
        self.session.add(
            DocumentTagLog(
                document_id=self.route1.document_id,
                document_type=ROUTE_TYPE,
                user_id=self.contributor.id,
                is_creation=True,
            )
        )

        self.session.flush()
