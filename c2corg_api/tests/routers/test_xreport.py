"""
Tests for the FastAPI xreport router (``/v2/xreports``).

Mirrors ``c2corg_api/tests/views/test_xreport.py`` — same test
data, same assertions — but exercises the new FastAPI code path
instead of Pyramid/Cornice.
"""

from datetime import date

from fastapi.testclient import TestClient

from c2corg_api.database import get_db
from c2corg_api.models.article import Article
from c2corg_api.models.association import Association, AssociationLog
from c2corg_api.models.common.attributes import QualityTypes
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.document_history import DocumentVersion
from c2corg_api.models.image import Image
from c2corg_api.models.outing import Outing
from c2corg_api.models.route import Route
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.models.waypoint import Waypoint
from c2corg_api.models.xreport import XREPORT_TYPE, Xreport, XreportLocale
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, global_tokens, global_userids, settings
from c2corg_api.tests.routers import get_real_app
from c2corg_api.routers.helpers.document_crud import create_new_version, update_version


class TestXreportFastAPIRouter(BaseTestCase):
    """Full test suite for ``/v2/xreports``.

    Mirrors ``TestXreportRest`` from
    ``tests/views/test_xreport.py``.
    """

    @classmethod
    def _get_app(cls):
        return get_real_app()

    def setUp(self):
        super().setUp()
        configure_security(settings)
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

    def _auth_headers(self, username='moderator'):
        token = global_tokens[username]
        return {'Authorization': f'JWT token="{token}"'}

    # ──────────────────────────────────────────────────────────
    # Test data  (mirrors TestXreportRest._add_test_data)
    # ──────────────────────────────────────────────────────────

    def _add_test_data(self):
        self.xreport1 = Xreport(
            event_activity='skitouring',
            event_type='stone_ice_fall',
            date=date(2020, 1, 1),
        )
        self.locale_en = XreportLocale(
            lang='en', title="Lac d'Annecy", place='some place descrip. in english'
        )
        self.locale_fr = XreportLocale(
            lang='fr', title="Lac d'Annecy", place='some place descrip. in french'
        )
        self.xreport1.locales.append(self.locale_en)
        self.xreport1.locales.append(self.locale_fr)
        self.session.add(self.xreport1)
        self.session.flush()

        user_id = global_userids['contributor']
        create_new_version(self.xreport1, user_id, db=self.session)
        self.xreport1_version = (
            self.session.query(DocumentVersion)
            .filter(DocumentVersion.document_id == self.xreport1.document_id)
            .filter(DocumentVersion.lang == 'en')
            .first()
        )

        # associate contributor3 to xreport1
        user_id3 = global_userids['contributor3']
        self._add_association(
            Association(
                parent_document_id=user_id3,
                parent_document_type=USERPROFILE_TYPE,
                child_document_id=self.xreport1.document_id,
                child_document_type=XREPORT_TYPE,
            ),
            user_id,
        )

        self.xreport2 = Xreport(
            event_activity='skitouring',
            event_type='avalanche',
            nb_participants=5,
            date=date(2021, 1, 1),
        )
        self.session.add(self.xreport2)
        self.xreport3 = Xreport(
            event_activity='skitouring',
            event_type='avalanche',
            nb_participants=5,
            date=date(2018, 1, 1),
        )
        self.session.add(self.xreport3)
        self.xreport4 = Xreport(
            event_activity='skitouring',
            event_type='avalanche',
            nb_participants=5,
            nb_impacted=5,
            age=50,
        )
        self.xreport4.locales.append(DocumentLocale(lang='en', title="Lac d'Annecy"))
        self.xreport4.locales.append(DocumentLocale(lang='fr', title="Lac d'Annecy"))
        self.session.add(self.xreport4)

        self.article2 = Article(
            categories=['site_info'], activities=['hiking'], article_type='collab'
        )
        self.session.add(self.article2)
        self.session.flush()

        self.image2 = Image(
            filename='image2.jpg', activities=['paragliding'], height=1500
        )
        self.session.add(self.image2)
        self.session.flush()

        self.waypoint1 = Waypoint(waypoint_type='summit', elevation=2203)
        self.session.add(self.waypoint1)
        self.waypoint2 = Waypoint(
            waypoint_type='climbing_outdoor',
            elevation=2,
            rock_types=[],
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
        )
        self.session.add(self.waypoint2)
        self.session.flush()

        self.outing3 = Outing(
            activities=['skitouring'],
            date_start=date(2016, 2, 1),
            date_end=date(2016, 2, 2),
        )
        self.session.add(self.outing3)
        self.route3 = Route(
            activities=['skitouring'],
            elevation_max=1500,
            elevation_min=700,
            height_diff_up=500,
            height_diff_down=500,
            durations=['1'],
        )
        self.session.add(self.route3)
        self.session.flush()

        self._add_association(
            Association.create(
                parent_document=self.outing3, child_document=self.xreport1
            ),
            user_id,
        )
        self._add_association(
            Association.create(
                parent_document=self.route3, child_document=self.xreport1
            ),
            user_id,
        )
        self.session.flush()

    def _add_association(self, association, user_id):
        self.session.add(association)
        self.session.add(association.get_log(user_id, is_creation=True))

    # ──────────────────────────────────────────────────────────
    # GET collection
    # ──────────────────────────────────────────────────────────

    def test_get_collection(self):
        resp = self.client.get('/v2/xreports')
        assert resp.status_code == 200
        body = resp.json()
        doc = body['documents'][0]
        assert 'geometry' in doc

    def test_get_collection_paginated(self):
        resp = self.client.get('/v2/xreports?offset=0&limit=0')
        assert resp.status_code == 200
        assert len(resp.json()['documents']) == 0
        assert resp.json()['total'] == 4

        resp = self.client.get('/v2/xreports?offset=0&limit=1')
        ids = [d['document_id'] for d in resp.json()['documents']]
        assert ids == [self.xreport4.document_id]
        assert resp.json()['total'] == 4

        resp = self.client.get('/v2/xreports?offset=0&limit=2')
        ids = [d['document_id'] for d in resp.json()['documents']]
        assert ids == [self.xreport4.document_id, self.xreport3.document_id]

        resp = self.client.get('/v2/xreports?offset=1&limit=2')
        ids = [d['document_id'] for d in resp.json()['documents']]
        assert ids == [self.xreport3.document_id, self.xreport2.document_id]

    def test_get_collection_lang(self):
        resp = self.client.get('/v2/xreports?pl=es')
        assert resp.status_code == 200
        body = resp.json()
        doc = body['documents'][0]
        locales = doc.get('locales')
        assert len(locales) == 1
        assert locales[0]['lang'] == 'fr'

    # ──────────────────────────────────────────────────────────
    # GET single
    # ──────────────────────────────────────────────────────────

    def test_get(self):
        resp = self.client.get(
            f'/v2/xreports/{self.xreport1.document_id}',
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert 'xreport' not in body

        assert 'author' in body
        author = body.get('author')
        assert global_userids['contributor'] == author.get('user_id')

        associations = body['associations']
        assert 'images' in associations
        assert 'articles' in associations
        assert 'outings' in associations
        assert 'routes' in associations

        linked_images = associations.get('images')
        assert len(linked_images) == 0
        linked_articles = associations.get('articles')
        assert len(linked_articles) == 0
        linked_outings = associations.get('outings')
        assert len(linked_outings) == 1
        linked_routes = associations.get('routes')
        assert len(linked_routes) == 1

        assert body.get('event_activity') == self.xreport1.event_activity
        assert 'nb_participants' in body
        assert 'nb_impacted' in body
        assert 'event_type' in body
        assert body.get('event_type') == 'stone_ice_fall'
        assert 'date' in body
        assert body.get('date') == '2020-01-01'

        locale_en = next(loc for loc in body.get('locales') if loc['lang'] == 'en')
        assert locale_en.get('place') == 'some place descrip. in english'
        locale_fr = next(loc for loc in body.get('locales') if loc['lang'] == 'fr')
        assert locale_fr.get('place') == 'some place descrip. in french'

    def test_get_as_guest(self):
        """Unauthenticated user should not see personal
        data."""
        resp = self.client.get(f'/v2/xreports/{self.xreport1.document_id}')
        assert resp.status_code == 200
        body = resp.json()

        assert 'author_status' not in body
        assert 'activity_rate' not in body
        assert 'age' not in body
        assert 'gender' not in body
        assert 'previous_injuries' not in body
        assert 'autonomy' not in body

    def test_get_as_contributor_not_author(self):
        """Non-author contributor should not see personal
        data."""
        resp = self.client.get(
            f'/v2/xreports/{self.xreport1.document_id}',
            headers=self._auth_headers('contributor2'),
        )
        assert resp.status_code == 200
        body = resp.json()

        assert 'author_status' not in body
        assert 'activity_rate' not in body
        assert 'age' not in body
        assert 'gender' not in body
        assert 'previous_injuries' not in body
        assert 'autonomy' not in body

    def test_get_as_moderator(self):
        """Moderator can see personal data."""
        resp = self.client.get(
            f'/v2/xreports/{self.xreport1.document_id}',
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200
        body = resp.json()

        # personal fields should be present (even if None
        # for this test doc, they should not be stripped)
        assert 'author_status' in body
        assert 'activity_rate' in body
        assert 'age' in body
        assert 'gender' in body
        assert 'previous_injuries' in body
        assert 'autonomy' in body

    def test_get_lang(self):
        resp = self.client.get(
            f'/v2/xreports/{self.xreport1.document_id}?l=en',
            headers=self._auth_headers('contributor'),
        )
        assert resp.status_code == 200
        body = resp.json()
        locales = body.get('locales')
        assert len(locales) == 1
        assert locales[0]['lang'] == 'en'

    def test_get_new_lang(self):
        resp = self.client.get(
            f'/v2/xreports/{self.xreport1.document_id}?l=it',
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body.get('locales')) == 0

    def test_get_404(self):
        resp = self.client.get(
            '/v2/xreports/9999999', headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 404

    def test_get_cooked(self):
        resp = self.client.get(f'/v2/xreports/{self.xreport1.document_id}?cook=en')
        assert resp.status_code == 200
        body = resp.json()
        assert 'cooked' in body
        assert 'locales' in body
        locales = body['locales']
        assert len(locales) == 1
        assert locales[0]['lang'] == 'en'

    def test_get_cooked_with_defaulting(self):
        resp = self.client.get(f'/v2/xreports/{self.xreport1.document_id}?cook=it')
        assert resp.status_code == 200
        body = resp.json()
        assert 'cooked' in body
        locale = body['locales'][0]
        assert locale['lang'] == 'fr'

    # ──────────────────────────────────────────────────────────
    # GET version
    # ──────────────────────────────────────────────────────────

    def test_get_version(self):
        url = '/v2/xreports/{}/{}/{}'.format(
            self.xreport1.document_id, 'en', self.xreport1_version.id
        )
        resp = self.client.get(url)
        assert resp.status_code == 200
        body = resp.json()
        assert 'document' in body
        assert 'version' in body
        assert 'previous_version_id' in body
        assert 'next_version_id' in body
        assert body['document']['document_id'] == self.xreport1.document_id
        assert body['version']['version_id'] == self.xreport1_version.id

    # ──────────────────────────────────────────────────────────
    # GET info
    # ──────────────────────────────────────────────────────────

    def test_get_info(self):
        resp = self.client.get(f'/v2/xreports/{self.xreport1.document_id}/en/info')
        assert resp.status_code == 200
        body = resp.json()
        assert 'document_id' in body
        assert 'locales' in body
        assert body['document_id'] == self.xreport1.document_id
        locale = body['locales'][0]
        assert locale['lang'] == 'en'

    def test_get_info_best_lang(self):
        resp = self.client.get(f'/v2/xreports/{self.xreport1.document_id}/es/info')
        assert resp.status_code == 200
        body = resp.json()
        locale = body['locales'][0]
        assert locale['lang'] == 'fr'

    def test_get_info_404(self):
        resp = self.client.get('/v2/xreports/9999999/en/info')
        assert resp.status_code == 404

    # ──────────────────────────────────────────────────────────
    # POST (create)
    # ──────────────────────────────────────────────────────────

    def test_post_error(self):
        """Empty body → validation error for event_activity."""
        resp = self.client.post(
            '/v2/xreports', json={}, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 400

    def test_post_missing_title(self):
        body_post = {
            'event_activity': 'skitouring',
            'event_type': 'stone_ice_fall',
            'nb_participants': 5,
            'locales': [{'lang': 'en'}],
        }
        resp = self.client.post(
            '/v2/xreports', json=body_post, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 400
        errors = resp.json()['errors']
        assert any('title' in e.get('name', '') for e in errors)

    def test_post_non_whitelisted_attribute(self):
        body = {
            'event_activity': 'skitouring',
            'event_type': 'stone_ice_fall',
            'nb_participants': 5,
            'protected': True,
            'locales': [
                {
                    'lang': 'en',
                    'place': 'some place description',
                    'title': "Lac d'Annecy",
                }
            ],
        }
        resp = self.client.post(
            '/v2/xreports', json=body, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 200
        doc_id = resp.json()['document_id']
        doc = self.session.get(Xreport, doc_id)
        assert not doc.protected

    def test_post_unauthenticated(self):
        resp = self.client.post(
            '/v2/xreports',
            json={
                'event_activity': 'skitouring',
                'locales': [{'lang': 'en', 'title': 'Test'}],
            },
        )
        assert resp.status_code == 403

    def test_post_success(self):
        body = {
            'document_id': 123456,
            'version': 567890,
            'event_activity': 'skitouring',
            'event_type': 'stone_ice_fall',
            'nb_participants': 5,
            'autonomy': 'autonomous',
            'activity_rate': 'activity_rate_m2',
            'supervision': 'professional_supervision',
            'qualification': 'federal_trainer',
            'associations': {
                'images': [{'document_id': self.image2.document_id}],
                'articles': [{'document_id': self.article2.document_id}],
            },
            'geometry': {
                'version': 1,
                'document_id': self.waypoint2.document_id,
                'geom': '{"type": "Point", "coordinates": [635956, 5723604]}',
            },
            'locales': [{'title': "Lac d'Annecy", 'lang': 'en'}],
        }
        resp = self.client.post(
            '/v2/xreports', json=body, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 200, resp.text
        doc_id = resp.json()['document_id']
        assert doc_id is not None

        doc = self.session.get(Xreport, doc_id)
        assert doc is not None

        version = doc.versions[0]
        archive_xreport = version.document_archive
        assert archive_xreport.event_activity == 'skitouring'
        assert archive_xreport.event_type == 'stone_ice_fall'
        assert archive_xreport.nb_participants == 5
        assert archive_xreport.autonomy == 'autonomous'
        assert archive_xreport.activity_rate == 'activity_rate_m2'
        assert archive_xreport.supervision == 'professional_supervision'
        assert archive_xreport.qualification == 'federal_trainer'

        archive_locale = version.document_locales_archive
        assert archive_locale.lang == 'en'
        assert archive_locale.title == "Lac d'Annecy"

        # xreports DO have geometry
        assert doc.geometry is not None

        # Association to image
        assoc_img = self.session.get(
            Association, (doc.document_id, self.image2.document_id)
        )
        assert assoc_img is not None

        assoc_img_log = (
            self.session.query(AssociationLog)
            .filter(AssociationLog.parent_document_id == doc.document_id)
            .filter(AssociationLog.child_document_id == self.image2.document_id)
            .first()
        )
        assert assoc_img_log is not None

        # Association to article
        assoc_art = self.session.get(
            Association, (doc.document_id, self.article2.document_id)
        )
        assert assoc_art is not None

        assoc_art_log = (
            self.session.query(AssociationLog)
            .filter(AssociationLog.parent_document_id == doc.document_id)
            .filter(AssociationLog.child_document_id == self.article2.document_id)
            .first()
        )
        assert assoc_art_log is not None

    def test_post_anonymous(self):
        from c2corg_api.routers.helpers import document_crud as crud

        # Simulate the configured anonymous user id
        crud._anonymous_user_id = global_userids['moderator']
        try:
            body = {
                'document_id': 111,
                'version': 1,
                'event_activity': 'skitouring',
                'event_type': 'stone_ice_fall',
                'nb_participants': 666,
                'nb_impacted': 666,
                'locales': [{'title': "Lac d'Annecy", 'lang': 'en'}],
                'anonymous': True,
            }
            resp = self.client.post(
                '/v2/xreports', json=body, headers=self._auth_headers('contributor')
            )
            assert resp.status_code == 200, resp.text
            doc_id = resp.json()['document_id']

            doc = self.session.get(Xreport, doc_id)
            assert doc is not None

            # The contributor should NOT be set as author in the version
            # history — the anonymous user id should be used instead.
            user_id = global_userids['contributor']
            version = doc.versions[0]
            meta_data = version.history_metadata
            assert meta_data.user_id != user_id
            assert meta_data.user_id == global_userids['moderator']
        finally:
            crud._anonymous_user_id = None

    # ──────────────────────────────────────────────────────────
    # PUT (update)
    # ──────────────────────────────────────────────────────────

    def test_put_wrong_document_id(self):
        body = {
            'document': {
                'document_id': '9999999',
                'version': self.xreport1.version,
                'event_activity': 'skitouring',
                'event_type': 'avalanche',
                'nb_participants': 5,
                'locales': [
                    {
                        'lang': 'en',
                        'title': "Lac d'Annecy",
                        'version': self.locale_en.version,
                    }
                ],
            }
        }
        resp = self.client.put(
            '/v2/xreports/9999999', json=body, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 404

    def test_put_wrong_document_version(self):
        body = {
            'document': {
                'document_id': self.xreport1.document_id,
                'version': -9999,
                'event_activity': 'skitouring',
                'event_type': 'avalanche',
                'nb_participants': 5,
                'locales': [
                    {
                        'lang': 'en',
                        'title': "Lac d'Annecy",
                        'version': self.locale_en.version,
                    }
                ],
            }
        }
        resp = self.client.put(
            f'/v2/xreports/{self.xreport1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 409

    def test_put_wrong_locale_version(self):
        body = {
            'document': {
                'document_id': self.xreport1.document_id,
                'version': self.xreport1.version,
                'event_activity': 'skitouring',
                'event_type': 'avalanche',
                'nb_participants': 5,
                'locales': [{'lang': 'en', 'title': "Lac d'Annecy", 'version': -9999}],
            }
        }
        resp = self.client.put(
            f'/v2/xreports/{self.xreport1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 409

    def test_put_wrong_ids(self):
        body = {
            'document': {
                'document_id': self.xreport1.document_id,
                'version': self.xreport1.version,
                'event_activity': 'skitouring',
                'event_type': 'avalanche',
                'nb_participants': 5,
                'locales': [
                    {
                        'lang': 'en',
                        'title': "Lac d'Annecy",
                        'version': self.locale_en.version,
                    }
                ],
            }
        }
        resp = self.client.put(
            f'/v2/xreports/{self.xreport1.document_id + 1}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 400

    def test_put_no_document(self):
        body = {'message': '...'}
        resp = self.client.put(
            f'/v2/xreports/{self.xreport1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 400

    def test_put_unauthenticated(self):
        body = {
            'document': {
                'document_id': self.xreport1.document_id,
                'version': self.xreport1.version,
                'event_activity': 'skitouring',
                'locales': [
                    {'lang': 'en', 'title': 'New', 'version': self.locale_en.version}
                ],
            }
        }
        resp = self.client.put(f'/v2/xreports/{self.xreport1.document_id}', json=body)
        assert resp.status_code == 403

    def test_put_success_all(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.xreport1.document_id,
                'version': self.xreport1.version,
                'quality': QualityTypes.draft,
                'event_activity': 'skitouring',
                'event_type': 'stone_ice_fall',
                'nb_participants': 333,
                'nb_impacted': 666,
                'age': 50,
                'rescue': False,
                'associations': {
                    'images': [{'document_id': self.image2.document_id}],
                    'articles': [{'document_id': self.article2.document_id}],
                },
                'geometry': {
                    'geom': '{"type": "Point", "coordinates": [635956, 5723604]}'
                },
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'New title',
                        'place': 'some NEW place descrip. in english',
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        resp = self.client.put(
            f'/v2/xreports/{self.xreport1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        xreport1 = self.session.get(Xreport, self.xreport1.document_id)

        assert xreport1.event_activity == 'skitouring'
        locale_en = xreport1.get_locale('en')
        assert locale_en.title == 'New title'

        versions = xreport1.versions
        version_en = sorted(
            [v for v in versions if v.lang == 'en'], key=lambda v: v.id, reverse=True
        )[0]
        assert version_en.document_locales_archive.title == 'New title'

        archive_doc = version_en.document_archive
        assert archive_doc.event_activity == 'skitouring'
        assert archive_doc.event_type == 'stone_ice_fall'
        assert archive_doc.nb_participants == 333
        assert archive_doc.nb_impacted == 666

        # xreports DO have geometry
        assert xreport1.geometry is not None

        # Association to image
        assoc_img = self.session.get(
            Association, (xreport1.document_id, self.image2.document_id)
        )
        assert assoc_img is not None

        # Association to article
        assoc_art = self.session.get(
            Association, (xreport1.document_id, self.article2.document_id)
        )
        assert assoc_art is not None

    def test_put_success_figures_only(self):
        body = {
            'message': 'Changing figures',
            'document': {
                'document_id': self.xreport1.document_id,
                'version': self.xreport1.version,
                'quality': QualityTypes.draft,
                'event_activity': 'skitouring',
                'event_type': 'stone_ice_fall',
                'nb_participants': 333,
                'nb_impacted': 666,
                'age': 50,
                'rescue': False,
                'locales': [
                    {
                        'lang': 'en',
                        'title': "Lac d'Annecy",
                        'place': 'some place descrip. in english',
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        resp = self.client.put(
            f'/v2/xreports/{self.xreport1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        xreport1 = self.session.get(Xreport, self.xreport1.document_id)
        assert xreport1.event_activity == 'skitouring'

    def test_put_success_lang_only(self):
        body = {
            'message': 'Changing lang',
            'document': {
                'document_id': self.xreport1.document_id,
                'version': self.xreport1.version,
                'quality': QualityTypes.draft,
                'event_activity': 'skitouring',
                'event_type': 'stone_ice_fall',
                'date': '2020-01-01',
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'New title',
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        resp = self.client.put(
            f'/v2/xreports/{self.xreport1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        xreport1 = self.session.get(Xreport, self.xreport1.document_id)
        assert xreport1.get_locale('en').title == 'New title'

    def test_put_success_new_lang(self):
        body = {
            'message': 'Adding lang',
            'document': {
                'document_id': self.xreport1.document_id,
                'version': self.xreport1.version,
                'quality': QualityTypes.draft,
                'event_activity': 'skitouring',
                'event_type': 'stone_ice_fall',
                'date': '2020-01-01',
                'locales': [{'lang': 'es', 'title': "Lac d'Annecy"}],
            },
        }
        resp = self.client.put(
            f'/v2/xreports/{self.xreport1.document_id}',
            json=body,
            headers=self._auth_headers('moderator'),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        xreport1 = self.session.get(Xreport, self.xreport1.document_id)
        assert xreport1.get_locale('es').title == "Lac d'Annecy"

    # ──────────────────────────────────────────────────────────
    # PUT — xreport-specific permission tests
    # ──────────────────────────────────────────────────────────

    def test_put_as_author(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.xreport1.document_id,
                'version': self.xreport1.version,
                'quality': QualityTypes.draft,
                'event_activity': 'sport_climbing',
                'event_type': 'person_fall',
                'age': 90,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Another final EN title',
                        'version': self.locale_en.version,
                    }
                ],
            },
        }
        resp = self.client.put(
            f'/v2/xreports/{self.xreport1.document_id}',
            json=body,
            headers=self._auth_headers('contributor'),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        xreport1 = self.session.get(Xreport, self.xreport1.document_id)
        versions = xreport1.versions
        version_en = sorted(
            [v for v in versions if v.lang == 'en'], key=lambda v: v.id, reverse=True
        )[0]
        archive_locale = version_en.document_locales_archive
        assert archive_locale.title == 'Another final EN title'

        archive_doc = version_en.document_archive
        assert archive_doc.event_activity == 'sport_climbing'
        assert archive_doc.event_type == 'person_fall'
        assert archive_doc.age == 90

    def test_put_as_associated_user(self):
        """contributor3 is associated to xreport1 and
        should be allowed to edit."""
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.xreport1.document_id,
                'version': self.xreport1.version,
                'quality': QualityTypes.draft,
                'event_activity': 'alpine_climbing',
                'event_type': 'crevasse_fall',
                'age': 25,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Renamed title by assoc. user',
                        'version': self.locale_en.version,
                    }
                ],
                'associations': {
                    'articles': [{'document_id': self.article2.document_id}],
                    'routes': [{'document_id': self.route3.document_id}],
                },
            },
        }
        resp = self.client.put(
            f'/v2/xreports/{self.xreport1.document_id}',
            json=body,
            headers=self._auth_headers('contributor3'),
        )
        assert resp.status_code == 200, resp.text

        self.session.expire_all()
        xreport1 = self.session.get(Xreport, self.xreport1.document_id)
        versions = xreport1.versions
        version_en = sorted(
            [v for v in versions if v.lang == 'en'], key=lambda v: v.id, reverse=True
        )[0]
        archive_locale = version_en.document_locales_archive
        assert archive_locale.title == 'Renamed title by assoc. user'

        archive_doc = version_en.document_archive
        assert archive_doc.event_activity == 'alpine_climbing'
        assert archive_doc.event_type == 'crevasse_fall'
        assert archive_doc.age == 25

    def test_put_as_non_author(self):
        """Non-author, non-moderator, non-associated user
        should be forbidden."""
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.xreport4.document_id,
                'version': self.xreport4.version,
                'quality': QualityTypes.draft,
                'event_activity': 'sport_climbing',
                'event_type': 'person_fall',
                'age': 90,
                'locales': [
                    {
                        'lang': 'en',
                        'title': 'Another final EN title',
                        'version': self.xreport4.locales[0].version,
                    }
                ],
            },
        }
        resp = self.client.put(
            f'/v2/xreports/{self.xreport4.document_id}',
            json=body,
            headers=self._auth_headers('contributor2'),
        )
        assert resp.status_code == 403
        body = resp.json()
        assert body['status'] == 'error'
        assert len(body['errors']) == 1
        assert body['errors'][0]['name'] == 'Forbidden'

    # ══════════════════════════════════════════════════════════
    #  POST — geometry / attribute validation
    # ══════════════════════════════════════════════════════════

    def test_post_wrong_geom_type(self):
        """LineString instead of Point → 400 with geometry error."""
        body = {
            'event_activity': 'skitouring',
            'event_type': 'stone_ice_fall',
            'nb_participants': 5,
            'geometry': {
                'geom': '{"type": "LineString", "coordinates": '
                '[[635956, 5723604], [635966, 5723644]]}'
            },
            'locales': [{'title': "Lac d'Annecy", 'lang': 'en'}],
        }
        resp = self.client.post(
            '/v2/xreports', json=body, headers=self._auth_headers('moderator')
        )
        assert resp.status_code == 400, resp.json()
        data = resp.json()
        errors = data['errors']
        assert any('POINT' in e.get('description', '') for e in errors), errors

    def test_post_outdated_attributes_error(self):
        """Outdated enum values → 400 with enum error per attribute."""
        outdated = [
            ('autonomy', 'initiator'),
            ('activity_rate', 'activity_rate_10'),
            ('event_type', 'roped_fall'),
            ('event_activity', 'hiking'),
        ]
        for key, value in outdated:
            body = {
                'event_activity': 'skitouring',
                'locales': [{'title': "Lac d'Annecy", 'lang': 'en'}],
            }
            body[key] = value
            resp = self.client.post(
                '/v2/xreports', json=body, headers=self._auth_headers('moderator')
            )
            assert resp.status_code in (400, 422), f'{key}={value}: {resp.json()}'
            data = resp.json()
            errors = data.get('errors', [])
            assert len(errors) >= 1, f'No errors for {key}={value}'

    def test_post_as_contributor_and_get_as_author(self):
        """Contributor creates xreport → they are recorded as author and
        can see personal fields when fetching."""
        body = {
            'event_activity': 'skitouring',
            'event_type': 'stone_ice_fall',
            'nb_participants': 666,
            'nb_impacted': 666,
            'locales': [{'title': "Lac d'Annecy", 'lang': 'en'}],
        }
        resp = self.client.post(
            '/v2/xreports', json=body, headers=self._auth_headers('contributor')
        )
        assert resp.status_code == 200, resp.json()
        doc_id = resp.json()['document_id']
        doc = self.session.get(Xreport, doc_id)
        assert doc is not None

        # contributor is recorded as the author
        user_id = global_userids['contributor']
        version = doc.versions[0]
        assert version.history_metadata.user_id == user_id

        # contributor (as author) can see personal fields
        resp = self.client.get(
            f'/v2/xreports/{doc_id}', headers=self._auth_headers('contributor')
        )
        assert resp.status_code == 200
        body = resp.json()
        assert 'author_status' in body
        assert 'activity_rate' in body
        assert 'age' in body
        assert 'gender' in body
        assert 'previous_injuries' in body
        assert 'autonomy' in body

    # ──────────────────────────────────────────────────────────
    # Association history
    # ──────────────────────────────────────────────────────────

    def test_get_associations_history(self):
        resp = self.client.get(
            f'/v2/associations-history?d={self.xreport1.document_id}'
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body['count'], int)
        assert body['count'] >= 1
        for entry in body['associations']:
            ids = (
                entry['parent_document']['document_id'],
                entry['child_document']['document_id'],
            )
            assert self.xreport1.document_id in ids
