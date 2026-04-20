"""
Tests that all supported languages work across FastAPI router endpoints.

Mirrors ``c2corg_api/tests/views/test_langs.py``.
Exercises collection GET, search, feed, article creation, user
preferences, and preferred-language update for every ``DefaultLangs``
value through the ``/v2/`` FastAPI routes.
"""

from datetime import date, datetime

from fastapi.testclient import TestClient

from c2corg_api.database import get_db
from c2corg_api.models.article import Article
from c2corg_api.models.common.attributes import DefaultLangs
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.feed import DocumentChange
from c2corg_api.models.outing import Outing, OutingLocale
from c2corg_api.models.user import User
from c2corg_api.models.waypoint import WAYPOINT_TYPE, Waypoint, WaypointLocale
from c2corg_api.routers.feed import configure_feed_router
from c2corg_api.scripts.es.fill_index import fill_index
from c2corg_api.security.fastapi_security import configure_security
from c2corg_api.tests import BaseTestCase, global_tokens, global_userids, settings
from c2corg_api.tests.routers import get_real_app
from c2corg_api.tests.search import force_search_index


class TestLangsRouter(BaseTestCase):
    """Verify every ``DefaultLangs`` value works across the main
    FastAPI router endpoints."""

    @classmethod
    def _get_app(cls):
        return get_real_app()

    def setUp(self):
        super().setUp()
        configure_security(settings)
        configure_feed_router(settings)

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

    # ── Test data ─────────────────────────────────────────────────

    def _add_test_data(self):
        waypoint = Waypoint(
            waypoint_type='summit',
            elevation=2000,
            geometry=DocumentGeometry(geom='SRID=3857;POINT(635956 5723604)'),
        )
        outing = Outing(
            activities=['skitouring'],
            date_start=date(2016, 1, 1),
            date_end=date(2016, 1, 1),
            geometry=DocumentGeometry(geom='SRID=3857;POINT(0 0)'),
        )
        article = Article(
            categories=['site_info'], activities=['hiking'], article_type='collab'
        )

        for lang in DefaultLangs:
            outing.locales.append(OutingLocale(lang=lang, title=f'Title in {lang}'))
            article.locales.append(DocumentLocale(lang=lang, title=f'Title in {lang}'))
            waypoint.locales.append(WaypointLocale(lang=lang, title=f'Title in {lang}'))

        self.session.add(article)
        self.session.add(outing)
        self.session.add(waypoint)
        self.session.flush()
        fill_index(self.session)
        force_search_index()

        contributor_id = global_userids['contributor']
        for lang in DefaultLangs:
            self.session.add(
                DocumentChange(
                    time=datetime(2016, 1, 1, 12, 0, 0),
                    user_id=contributor_id,
                    change_type='created',
                    document_id=waypoint.document_id,
                    document_type=WAYPOINT_TYPE,
                    user_ids=[contributor_id],
                    langs=[lang],
                )
            )
        self.session.flush()

    # ── Tests ─────────────────────────────────────────────────────

    def test_get_collection(self):
        for lang in DefaultLangs:
            r = self.client.get(f'/v2/outings?pl={lang}')
            assert r.status_code == 200, f'lang={lang}: {r.status_code}'
            body = r.json()
            assert body['total'] != 0, f'lang={lang}: empty'

    def test_search(self):
        for lang in DefaultLangs:
            r = self.client.get(f'/v2/search?q=Title&pl={lang}')
            assert r.status_code == 200, f'lang={lang}: {r.status_code}'
            body = r.json()
            assert body['articles']['total'] != 0, f'lang={lang}: no articles'

    def test_feed(self):
        for lang in DefaultLangs:
            r = self.client.get(f'/v2/feed?pl={lang}')
            assert r.status_code == 200, f'lang={lang}: {r.status_code}'
            body = r.json()
            assert len(body['feed']) != 0, f'lang={lang}: empty feed'

    def test_create(self):
        for lang in DefaultLangs:
            body = {
                'article_type': 'collab',
                'locales': [{'lang': lang, 'title': 'Title'}],
            }
            r = self.client.post(
                '/v2/articles', json=body, headers=self._auth_headers('contributor')
            )
            assert r.status_code == 200, f'lang={lang}: {r.status_code} {r.text}'
            doc_id = r.json()['document_id']

            r2 = self.client.get(f'/v2/articles/{doc_id}')
            assert r2.status_code == 200
            assert r2.json()['locales'][0]['lang'] == lang

            # Reset rate-limit counter so the next iteration
            # is not throttled.
            user = self.session.get(User, global_userids['contributor'])
            user.ratelimit_times = 0

    def test_user_preferences(self):
        user_id = global_userids['contributor']

        for lang in DefaultLangs:
            request_body = {
                'followed_only': True,
                'activities': [],
                'langs': [lang],
                'areas': [],
            }
            r = self.client.post(
                '/v2/users/preferences',
                json=request_body,
                headers=self._auth_headers('contributor'),
            )
            assert r.status_code == 200, f'lang={lang}: POST {r.status_code} {r.text}'

            r2 = self.client.get(
                '/v2/users/preferences', headers=self._auth_headers('contributor')
            )
            assert r2.status_code == 200
            assert r2.json()['langs'] == [lang], (
                f'lang={lang}: expected [{lang}], got {r2.json()["langs"]}'
            )

            user = self.session.get(User, user_id)
            user.ratelimit_times = 0

    def test_preferred_lang(self):
        user_id = global_userids['contributor']

        for lang in DefaultLangs:
            r = self.client.post(
                '/v2/users/update_preferred_language',
                json={'lang': lang},
                headers=self._auth_headers('contributor'),
            )
            assert r.status_code == 200, f'lang={lang}: {r.status_code} {r.text}'

            user = self.session.get(User, user_id)
            self.session.expunge(user)
            user = self.session.get(User, user_id)
            assert user.lang == lang, f'expected {lang}, got {user.lang}'
