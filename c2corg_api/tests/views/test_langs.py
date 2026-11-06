from datetime import date, datetime

import pytest

from c2corg_api.models.article import Article
from c2corg_api.models.common.attributes import default_langs
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.feed import DocumentChange
from c2corg_api.models.outing import Outing, OutingLocale
from c2corg_api.models.user import User
from c2corg_api.models.waypoint import WAYPOINT_TYPE, Waypoint, WaypointLocale
from c2corg_api.scripts.es.fill_index import fill_index
from c2corg_api.tests import auth_headers, send_json
from c2corg_api.tests.search import force_search_index


class TestLangs:
    @pytest.fixture(autouse=True)
    def _setup_test_langs(self, client, session, user_ids):

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

        for lang in default_langs:
            locale = OutingLocale(lang=lang, title=f'Title in {lang}')
            outing.locales.append(locale)

            locale = DocumentLocale(lang=lang, title=f'Title in {lang}')
            article.locales.append(locale)

            locale = WaypointLocale(lang=lang, title=f'Title in {lang}')
            waypoint.locales.append(locale)

        session.add(article)
        session.add(outing)
        session.add(waypoint)
        session.flush()
        fill_index(session)
        # make sure the search index is built
        force_search_index()

        contributor_id = user_ids['contributor']

        for lang in default_langs:
            session.add(
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

        session.flush()

    def get_with_auth(self, client, prefix):
        headers = auth_headers(username='contributor')
        return client.get(prefix, headers=headers, status=200)

    def post_with_auth(self, client, prefix, body):
        headers = auth_headers(username='contributor')
        return send_json(client, 'post', prefix, body, headers=headers, status=200)

    def test_get_collection(self, client):
        for lang in default_langs:
            body = client.get(f'/outings?l={lang}', status=200).json
            assert body['total'] != 0

    def test_search(self, client):
        for lang in default_langs:
            response = client.get(f'/search?q=Title&pl={lang}', status=200)
            body = response.json
            assert body['articles']['total'] != 0

    def test_feed(self, client):
        for lang in default_langs:
            response = client.get(f'/feed?pl={lang}', status=200)
            body = response.json
            assert len(body['feed']) != 0

    def test_create(self, client):
        for lang in default_langs:
            body = {
                'article_type': 'collab',
                'locales': [{'lang': lang, 'title': 'Title'}],
            }

            document = self.post_with_auth(client, '/articles', body).json

            document = client.get(f'/articles/{document["document_id"]}')
            assert lang == document.json['locales'][0]['lang']

    def test_user_preferences(self, client, session, user_ids):
        user_id = user_ids['contributor']

        for lang in default_langs:
            request_body = {
                'followed_only': True,
                'activities': [],
                'langs': [lang],
                'areas': [],
            }

            self.post_with_auth(client, '/users/preferences', request_body)

            json = self.get_with_auth(client, '/users/preferences').json

            assert [lang] == json['langs']

            user = session.get(User, user_id)
            user.ratelimit_times = 0

    def test_preferred_lang(self, client, session, user_ids):
        for lang in default_langs:
            body = {'lang': lang}
            self.post_with_auth(client, '/users/update_preferred_language', body)

            user_id = user_ids['contributor']

            user = session.get(User, user_id)
            session.expunge(user)

            user = session.get(User, user_id)
            assert user.lang == lang
