"""
Tests for the FastAPI association router (``/v2/associations``).

Mirrors ``c2corg_api/tests/views/test_association.py`` — same test data,
same assertions — but exercises the new FastAPI code path.
"""

from datetime import date

from fastapi.testclient import TestClient

from c2corg_api.database import get_db
from c2corg_api.models.article import Article
from c2corg_api.models.association import Association, AssociationLog
from c2corg_api.models.document import DocumentLocale
from c2corg_api.models.feed import update_feed_document_create
from c2corg_api.models.image import Image
from c2corg_api.models.outing import OUTING_TYPE, Outing
from c2corg_api.models.route import Route
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.models.waypoint import Waypoint
from c2corg_api.models.xreport import Xreport, XreportLocale
from c2corg_api.routers.association import configure_association_router
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, global_tokens, global_userids, settings
from c2corg_api.tests.routers import get_real_app
from c2corg_api.routers.helpers.document_crud import create_new_version, update_version


class TestAssociationFastAPIRouter(BaseTestCase):
    prefix = '/v2/associations'

    @classmethod
    def _get_app(cls):
        return get_real_app()

    def setUp(self):
        super().setUp()

        configure_security(settings)
        configure_association_router(self.queue_config)
        self._add_test_data()

        app = self._get_app()

        def _override_get_db():
            yield self.session

        app.dependency_overrides[get_db] = _override_get_db

        self.client = TestClient(app, raise_server_exceptions=False)

    def tearDown(self):
        app = self._get_app()
        app.dependency_overrides.pop(get_db, None)
        super().tearDown()

    def _auth_headers(self, username='contributor'):
        token = global_tokens[username]
        return {'Authorization': f'JWT token="{token}"'}

    def check_cache_version(self, document_id, version):
        from c2corg_api.models.cache_version import CacheVersion

        cache_version = self.session.get(CacheVersion, document_id)
        assert cache_version is not None
        assert cache_version is not None
        assert cache_version.version == version

    def get_feed_change(self, document_id, change_type=None):
        from c2corg_api.models.feed import DocumentChange

        q = self.session.query(DocumentChange).filter(
            DocumentChange.document_id == document_id
        )
        if change_type:
            q = q.filter(DocumentChange.change_type == change_type)
        return q.first()

    # ──────────────────────────────────────────────────────────────
    # POST (create) tests
    # ──────────────────────────────────────────────────────────────

    def test_add_association_unauthorized(self):
        r = self.client.post(
            self.prefix, json={'parent_document_id': 1, 'child_document_id': 2}
        )
        assert r.status_code == 403

    def test_add_association(self):
        request_body = {
            'parent_document_id': self.waypoint1.document_id,
            'child_document_id': self.waypoint2.document_id,
        }
        r = self.client.post(
            self.prefix, json=request_body, headers=self._auth_headers('contributor')
        )
        assert r.status_code == 200

        association = self.session.get(
            Association, (self.waypoint1.document_id, self.waypoint2.document_id)
        )
        assert association is not None

        association_log = (
            self.session.query(AssociationLog)
            .filter(AssociationLog.parent_document_id == self.waypoint1.document_id)
            .filter(AssociationLog.child_document_id == self.waypoint2.document_id)
            .one()
        )
        assert association_log.is_creation
        assert association_log.user_id is not None

        queue = self.queue_config.queue(self.queue_config.connection)
        assert queue.get() is not None, 'no sync. notification sent for ES'

        self.check_cache_version(self.waypoint1.document_id, 2)
        self.check_cache_version(self.waypoint2.document_id, 2)

    def test_add_association_wa(self):
        request_body = {
            'parent_document_id': self.waypoint1.document_id,
            'child_document_id': self.article1.document_id,
        }
        r = self.client.post(
            self.prefix, json=request_body, headers=self._auth_headers('contributor')
        )
        assert r.status_code == 200

        association = self.session.get(
            Association, (self.waypoint1.document_id, self.article1.document_id)
        )
        assert association is not None

        self.check_cache_version(self.waypoint1.document_id, 2)
        self.check_cache_version(self.article1.document_id, 2)

    def test_add_association_uo(self):
        contributor2 = global_userids['contributor2']
        request_body = {
            'parent_document_id': contributor2,
            'child_document_id': self.outing.document_id,
        }
        r = self.client.post(
            self.prefix, json=request_body, headers=self._auth_headers('contributor')
        )
        assert r.status_code == 200

        association = self.session.get(
            Association, (contributor2, self.outing.document_id)
        )
        assert association is not None

        # check that the feed change is updated
        feed_change = self.get_feed_change(
            self.outing.document_id, change_type='updated'
        )
        assert feed_change is not None
        assert feed_change is not None
        assert feed_change.change_type == 'updated'
        assert set(feed_change.user_ids) == set(
            [global_userids['contributor'], global_userids['contributor2']]
        )

        # check that the participants of the 2nd feed change are also updated
        feed_change = self.get_feed_change(
            self.outing.document_id, change_type='added_photos'
        )
        assert feed_change is not None
        assert feed_change is not None
        assert set(feed_change.user_ids) == set(
            [
                global_userids['contributor'],
                global_userids['contributor2'],
                global_userids['moderator'],
            ]
        )

    def test_add_association_uo_no_rights(self):
        """Check that associations with outings can only be changed by users
        associated to the outing or moderators.
        """
        contributor2 = global_userids['contributor2']
        request_body = {
            'parent_document_id': contributor2,
            'child_document_id': self.outing.document_id,
        }
        r = self.client.post(
            self.prefix, json=request_body, headers=self._auth_headers('contributor2')
        )
        assert r.status_code == 400
        body = r.json()
        assert body.get('status') == 'error'
        errors = body['errors']
        assert any(
            e.get('name') == 'associations.outings'
            and e.get('description')
            == 'no rights to modify associations with outing {}'.format(
                self.outing.document_id
            )
            for e in errors
        )

    def test_add_association_duplicate(self):
        """Test that there is only one association between two documents."""
        request_body = {
            'parent_document_id': self.waypoint1.document_id,
            'child_document_id': self.waypoint2.document_id,
        }
        headers = self._auth_headers('contributor')

        # first association, ok
        r = self.client.post(self.prefix, json=request_body, headers=headers)
        assert r.status_code == 200

        # 2nd association, fail
        r = self.client.post(self.prefix, json=request_body, headers=headers)
        assert r.status_code == 400

        # back-link association also fails
        request_body = {
            'parent_document_id': self.waypoint2.document_id,
            'child_document_id': self.waypoint1.document_id,
        }
        r = self.client.post(self.prefix, json=request_body, headers=headers)
        assert r.status_code == 400

    def test_add_association_invalid(self):
        request_body = {
            'parent_document_id': self.route1.document_id,
            'child_document_id': self.waypoint2.document_id,
        }
        r = self.client.post(
            self.prefix, json=request_body, headers=self._auth_headers('contributor')
        )
        assert r.status_code == 400
        body = r.json()
        assert body.get('status') == 'error'
        errors = body['errors']
        found = False
        for error in errors:
            if (
                error.get('name') == 'association'
                and error.get('description') == 'invalid association type'
            ):
                found = True
        assert found

    def test_add_association_redirected_document(self):
        request_body = {
            'parent_document_id': self.waypoint1.document_id,
            'child_document_id': self.waypoint3.document_id,
        }
        r = self.client.post(
            self.prefix, json=request_body, headers=self._auth_headers('contributor')
        )
        assert r.status_code == 400
        body = r.json()
        assert body.get('status') == 'error'
        errors = body['errors']
        found = False
        for error in errors:
            if error.get('name') == 'child_document_id':
                found = True
        assert found

    def test_add_association_invalid_ids(self):
        request_body = {'parent_document_id': -99, 'child_document_id': -999}
        r = self.client.post(
            self.prefix, json=request_body, headers=self._auth_headers('contributor')
        )
        assert r.status_code == 400
        body = r.json()
        assert body.get('status') == 'error'
        errors = body['errors']
        parent_error = any(e.get('name') == 'parent_document_id' for e in errors)
        child_error = any(e.get('name') == 'child_document_id' for e in errors)
        assert parent_error
        assert child_error

    def test_add_association_no_es_update(self):
        """Tests that the search index is only updated for specific
        association types.
        """
        request_body = {
            'parent_document_id': self.waypoint1.document_id,
            'child_document_id': self.image1.document_id,
        }
        r = self.client.post(
            self.prefix, json=request_body, headers=self._auth_headers('contributor')
        )
        assert r.status_code == 200

        queue = self.queue_config.queue(self.queue_config.connection)
        assert queue.get() is None, 'unexpected sync. notification sent for ES'

    # ── Personal article / image / xreport permission tests ──────

    def test_add_association_wc_article_collab(self):
        """Anyone can associate with a collab article."""
        request_body = {
            'parent_document_id': self.waypoint1.document_id,
            'child_document_id': self.article1.document_id,
        }
        r = self.client.post(
            self.prefix, json=request_body, headers=self._auth_headers('contributor2')
        )
        assert r.status_code == 200

    def test_add_association_wc_article_personal_unauthorized(self):
        """Non-creator cannot associate with a personal article."""
        self.article1.article_type = 'personal'
        self.session.flush()

        request_body = {
            'parent_document_id': self.waypoint1.document_id,
            'child_document_id': self.article1.document_id,
        }
        r = self.client.post(
            self.prefix, json=request_body, headers=self._auth_headers('contributor2')
        )
        assert r.status_code == 400
        errors = r.json()['errors']
        assert any(
            e.get('name') == 'associations.articles'
            and e.get('description')
            == 'no rights to modify associations with article {}'.format(
                self.article1.document_id
            )
            for e in errors
        )

    def test_add_association_wc_article_personal_authorized(self):
        """Creator can associate with their own personal article."""
        self.article1.article_type = 'personal'
        self.session.flush()

        request_body = {
            'parent_document_id': self.waypoint1.document_id,
            'child_document_id': self.article1.document_id,
        }
        r = self.client.post(
            self.prefix, json=request_body, headers=self._auth_headers('contributor')
        )
        assert r.status_code == 200

    def test_add_association_cc_article_personal_unauthorized(self):
        """Non-creator cannot associate with a personal article (article2)."""
        request_body = {
            'parent_document_id': self.article2.document_id,
            'child_document_id': self.article1.document_id,
        }
        r = self.client.post(
            self.prefix, json=request_body, headers=self._auth_headers('contributor2')
        )
        assert r.status_code == 400
        errors = r.json()['errors']
        assert any(
            e.get('name') == 'associations.articles'
            and e.get('description')
            == 'no rights to modify associations with article {}'.format(
                self.article2.document_id
            )
            for e in errors
        )

    def test_add_association_wi_image_personal_unauthorized(self):
        """Non-creator cannot associate with a personal image."""
        self.image1.image_type = 'personal'
        self.session.flush()

        request_body = {
            'parent_document_id': self.waypoint1.document_id,
            'child_document_id': self.image1.document_id,
        }
        r = self.client.post(
            self.prefix, json=request_body, headers=self._auth_headers('contributor2')
        )
        assert r.status_code == 400
        errors = r.json()['errors']
        assert any(
            e.get('name') == 'associations.images'
            and e.get('description')
            == 'no rights to modify associations with image {}'.format(
                self.image1.document_id
            )
            for e in errors
        )

    def test_add_association_wi_image_personal_authorized(self):
        """Creator can associate with their own image."""
        request_body = {
            'parent_document_id': self.waypoint1.document_id,
            'child_document_id': self.image1.document_id,
        }
        r = self.client.post(
            self.prefix, json=request_body, headers=self._auth_headers('contributor')
        )
        assert r.status_code == 200

    def test_add_association_wx_xreport_unauthorized(self):
        """Non-creator cannot associate with an xreport."""
        request_body = {
            'parent_document_id': self.waypoint1.document_id,
            'child_document_id': self.report1.document_id,
        }
        r = self.client.post(
            self.prefix, json=request_body, headers=self._auth_headers('contributor2')
        )
        assert r.status_code == 400
        errors = r.json()['errors']
        assert any(
            e.get('name') == 'associations.xreports'
            and e.get('description')
            == 'no rights to modify associations with xreport {}'.format(
                self.report1.document_id
            )
            for e in errors
        )

    def test_add_association_wx_xreport_authorized(self):
        """Creator can associate with their own xreport."""
        request_body = {
            'parent_document_id': self.waypoint1.document_id,
            'child_document_id': self.report1.document_id,
        }
        r = self.client.post(
            self.prefix, json=request_body, headers=self._auth_headers('contributor')
        )
        assert r.status_code == 200

    def test_add_association_wc_xreport_article_unauthorized(self):
        """Both xreport and personal article reject non-creator."""
        self.article1.article_type = 'personal'
        self.session.flush()

        request_body = {
            'parent_document_id': self.report1.document_id,
            'child_document_id': self.article1.document_id,
        }
        r = self.client.post(
            self.prefix, json=request_body, headers=self._auth_headers('contributor2')
        )
        assert r.status_code == 400
        errors = r.json()['errors']
        assert any(
            e.get('name') == 'associations.xreports'
            and e.get('description')
            == 'no rights to modify associations with xreport {}'.format(
                self.report1.document_id
            )
            for e in errors
        )
        assert any(
            e.get('name') == 'associations.articles'
            and e.get('description')
            == 'no rights to modify associations with article {}'.format(
                self.article1.document_id
            )
            for e in errors
        )

    # ──────────────────────────────────────────────────────────────
    # DELETE tests
    # ──────────────────────────────────────────────────────────────

    def test_delete_association_unauthorized(self):
        r = self.client.request(
            'DELETE',
            self.prefix,
            json={'parent_document_id': 1, 'child_document_id': 2},
        )
        assert r.status_code == 403

    def test_delete_association_not_existing(self):
        request_body = {
            'parent_document_id': self.waypoint1.document_id,
            'child_document_id': self.waypoint2.document_id,
        }
        r = self.client.request(
            'DELETE',
            self.prefix,
            json=request_body,
            headers=self._auth_headers('contributor'),
        )
        assert r.status_code == 400

    def test_delete_association(self):
        request_body = {
            'parent_document_id': self.waypoint1.document_id,
            'child_document_id': self.waypoint2.document_id,
        }
        headers = self._auth_headers('moderator')

        # add association
        r = self.client.post(self.prefix, json=request_body, headers=headers)
        assert r.status_code == 200

        # then delete it again
        r = self.client.request(
            'DELETE', self.prefix, json=request_body, headers=headers
        )
        assert r.status_code == 200

        self.session.expire_all()
        association = self.session.get(
            Association, (self.waypoint1.document_id, self.waypoint2.document_id)
        )
        assert association is None

        logs = (
            self.session.query(AssociationLog)
            .filter(AssociationLog.parent_document_id == self.waypoint1.document_id)
            .filter(AssociationLog.child_document_id == self.waypoint2.document_id)
            .order_by(AssociationLog.written_at)
            .all()
        )
        assert logs[0].is_creation
        assert not logs[1].is_creation

        queue = self.queue_config.queue(self.queue_config.connection)
        assert queue.get() is not None, 'no sync. notification sent for ES'

        self.check_cache_version(self.waypoint1.document_id, 3)
        self.check_cache_version(self.waypoint2.document_id, 3)

    def test_delete_association_non_moderator(self):
        """For non-personal documents, a normal user can create associations
        but not delete them.
        """
        request_body = {
            'parent_document_id': self.waypoint1.document_id,
            'child_document_id': self.waypoint2.document_id,
        }
        headers = self._auth_headers('contributor')

        # add association
        r = self.client.post(self.prefix, json=request_body, headers=headers)
        assert r.status_code == 200

        # then try to delete it again
        r = self.client.request(
            'DELETE', self.prefix, json=request_body, headers=headers
        )
        assert r.status_code == 400

    def test_delete_association_fuzzy(self):
        """Test that an association {parent: x, child: y} can be
        deleted with {parent: y, child: x}.
        """
        request_body = {
            'parent_document_id': self.waypoint1.document_id,
            'child_document_id': self.waypoint2.document_id,
        }
        headers = self._auth_headers('moderator')

        # add association
        r = self.client.post(self.prefix, json=request_body, headers=headers)
        assert r.status_code == 200

        # delete with swapped ids
        request_body = {
            'parent_document_id': self.waypoint2.document_id,
            'child_document_id': self.waypoint1.document_id,
        }
        r = self.client.request(
            'DELETE', self.prefix, json=request_body, headers=headers
        )
        assert r.status_code == 200

        self.session.expire_all()
        association = self.session.get(
            Association, (self.waypoint1.document_id, self.waypoint2.document_id)
        )
        assert association is None

    def test_delete_association_main_waypoint(self):
        request_body = {
            'parent_document_id': self.waypoint2.document_id,
            'child_document_id': self.route1.document_id,
        }
        headers = self._auth_headers('contributor')

        # add association
        r = self.client.post(self.prefix, json=request_body, headers=headers)
        assert r.status_code == 200

        # make the wp the main waypoint of the route
        self.route1.main_waypoint_id = self.waypoint2.document_id
        self.session.flush()

        # then try to delete the association
        r = self.client.request(
            'DELETE', self.prefix, json=request_body, headers=headers
        )
        assert r.status_code == 400

    def test_delete_association_wp_r_last_waypoint(self):
        request_body1 = {
            'parent_document_id': self.waypoint2.document_id,
            'child_document_id': self.route1.document_id,
        }
        headers = self._auth_headers('moderator')

        # add association
        r = self.client.post(self.prefix, json=request_body1, headers=headers)
        assert r.status_code == 200

        # try to delete — should fail (last waypoint)
        r = self.client.request(
            'DELETE', self.prefix, json=request_body1, headers=headers
        )
        assert r.status_code == 400

        # add a second waypoint
        request_body2 = {
            'parent_document_id': self.waypoint1.document_id,
            'child_document_id': self.route1.document_id,
        }
        r = self.client.post(self.prefix, json=request_body2, headers=headers)
        assert r.status_code == 200

        # now, the first waypoint can be unlinked
        r = self.client.request(
            'DELETE', self.prefix, json=request_body1, headers=headers
        )
        assert r.status_code == 200

    def test_delete_association_ro_last_route(self):
        request_body1 = {
            'parent_document_id': self.route1.document_id,
            'child_document_id': self.outing.document_id,
        }
        headers = self._auth_headers('moderator')

        # add association
        r = self.client.post(self.prefix, json=request_body1, headers=headers)
        assert r.status_code == 200

        # try to delete — should fail (last route)
        r = self.client.request(
            'DELETE', self.prefix, json=request_body1, headers=headers
        )
        assert r.status_code == 400

        # add a second route
        request_body2 = {
            'parent_document_id': self.route2.document_id,
            'child_document_id': self.outing.document_id,
        }
        r = self.client.post(self.prefix, json=request_body2, headers=headers)
        assert r.status_code == 200

        # now, the first route can be unlinked
        r = self.client.request(
            'DELETE', self.prefix, json=request_body1, headers=headers
        )
        assert r.status_code == 200

    def test_delete_association_uo(self):
        """Creator of the outing can delete user-outing association."""
        request_body = {
            'parent_document_id': global_userids['contributor'],
            'child_document_id': self.outing.document_id,
        }
        headers = self._auth_headers('contributor')

        r = self.client.request(
            'DELETE', self.prefix, json=request_body, headers=headers
        )
        assert r.status_code == 200

    def test_delete_association_uo_no_rights(self):
        """Non-creator of the outing cannot delete user-outing association."""
        user_id = global_userids['contributor']
        request_body = {
            'parent_document_id': user_id,
            'child_document_id': self.outing.document_id,
        }
        headers = self._auth_headers('contributor2')

        r = self.client.request(
            'DELETE', self.prefix, json=request_body, headers=headers
        )
        assert r.status_code == 400
        errors = r.json()['errors']
        assert any(
            e.get('name') == 'Bad Request'
            and e.get('description')
            == (
                'no rights to modify associations between document u ({}) and o ({})'
            ).format(user_id, self.outing.document_id)
            for e in errors
        )

    def test_delete_association_wc_article_personal(self):
        """Non-creator cannot delete association with a personal article."""
        # first add the association as the creator
        request_body = {
            'parent_document_id': self.waypoint1.document_id,
            'child_document_id': self.article2.document_id,
        }
        r = self.client.post(
            self.prefix, json=request_body, headers=self._auth_headers('contributor')
        )
        assert r.status_code == 200

        # try to delete as another user
        r = self.client.request(
            'DELETE',
            self.prefix,
            json=request_body,
            headers=self._auth_headers('contributor2'),
        )
        assert r.status_code == 400
        errors = r.json()['errors']
        assert any(
            e.get('name') == 'Bad Request'
            and e.get('description')
            == (
                'no rights to modify associations between document w ({}) and c ({})'
            ).format(self.waypoint1.document_id, self.article2.document_id)
            for e in errors
        )

    # ──────────────────────────────────────────────────────────────
    # Test data
    # ──────────────────────────────────────────────────────────────

    def _add_test_data(self):
        user_id = global_userids['contributor']

        self.waypoint1 = Waypoint(waypoint_type='summit', elevation=2203)
        self.session.add(self.waypoint1)

        self.waypoint2 = Waypoint(waypoint_type='summit', elevation=200)
        self.session.add(self.waypoint2)
        self.session.flush()

        self.waypoint3 = Waypoint(
            waypoint_type='summit',
            elevation=200,
            redirects_to=self.waypoint1.document_id,
        )
        self.session.add(self.waypoint3)

        self.route1 = Route(activities=['skitouring'])
        self.session.add(self.route1)

        self.route2 = Route(activities=['skitouring'])
        self.session.add(self.route2)

        self.image1 = Image(
            filename='image.jpg',
            locales=[DocumentLocale(lang='en', title='Mont Blanc from the air')],
        )
        self.session.add(self.image1)
        self.session.flush()
        create_new_version(self.image1, user_id, db=self.session)

        self.article1 = Article(
            categories=['site_info'],
            activities=['hiking'],
            article_type='collab',
            locales=[DocumentLocale(lang='en', title="Lac d'Annecy")],
        )
        self.session.add(self.article1)
        self.session.flush()
        create_new_version(self.article1, user_id, db=self.session)

        self.article2 = Article(
            categories=['site_info'],
            activities=['hiking'],
            article_type='personal',
            locales=[DocumentLocale(lang='en', title="Lac d'Annecy")],
        )
        self.session.add(self.article2)
        self.session.flush()
        create_new_version(self.article2, user_id, db=self.session)

        self.report1 = Xreport(
            event_activity='alpine_climbing',
            locales=[XreportLocale(lang='en', title="Lac d'Annecy")],
        )
        self.session.add(self.report1)
        self.session.flush()
        create_new_version(self.report1, user_id, db=self.session)

        self.outing = Outing(
            activities=['skitouring'],
            date_start=date(2016, 1, 1),
            date_end=date(2016, 1, 1),
        )
        self.session.add(self.outing)
        self.session.flush()

        self.session.add(
            Association(
                parent_document_id=user_id,
                parent_document_type=USERPROFILE_TYPE,
                child_document_id=self.outing.document_id,
                child_document_type=OUTING_TYPE,
            )
        )

        update_feed_document_create(self.outing, user_id)
        self.session.flush()

        # create a 2nd feed entry for the outing
        feed_change = self.get_feed_change(self.outing.document_id)
        assert feed_change is not None
        user_id_mod = global_userids['moderator']
        feed_change2 = feed_change.copy()
        feed_change2.change_type = 'added_photos'
        feed_change2.user_id = user_id_mod
        feed_change2.user_ids = list(set(feed_change.user_ids).union([user_id_mod]))
        self.session.add(feed_change2)
        self.session.flush()
