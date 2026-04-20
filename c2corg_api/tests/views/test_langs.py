from datetime import date, datetime

from c2corg_api.models.article import Article
from c2corg_api.models.common.attributes import DefaultLangs
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.feed import DocumentChange
from c2corg_api.models.outing import Outing, OutingLocale
from c2corg_api.models.user import User
from c2corg_api.models.waypoint import WAYPOINT_TYPE, Waypoint, WaypointLocale
from c2corg_api.scripts.es.fill_index import fill_index
from c2corg_api.tests.search import force_search_index
from c2corg_api.tests.views import BaseTestRest


class TestLangs(BaseTestRest):
    def setUp(self):
        BaseTestRest.setUp(self)

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
            locale = OutingLocale(lang=lang, title=f'Title in {lang}')
            outing.locales.append(locale)

            locale = DocumentLocale(lang=lang, title=f'Title in {lang}')
            article.locales.append(locale)

            locale = WaypointLocale(lang=lang, title=f'Title in {lang}')
            waypoint.locales.append(locale)

        self.session.add(article)
        self.session.add(outing)
        self.session.add(waypoint)
        self.session.flush()
        fill_index(self.session)
        # make sure the search index is built
        force_search_index()

        contributor_id = self.global_userids['contributor']

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

    def get_with_auth(self, prefix):
        headers = self.add_authorization_header(username='contributor')
        return self.app.get(prefix, headers=headers, status=200)

    def post_with_auth(self, prefix, body):
        headers = self.add_authorization_header(username='contributor')
        return self.app_post_json(prefix, body, headers=headers, status=200)

    def test_get_collection(self):
        for lang in DefaultLangs:
            body = self.app.get(f'/outings?l={lang}', status=200).json
            assert body['total'] != 0

    def test_search(self):
        for lang in DefaultLangs:
            response = self.app.get(f'/search?q=Title&pl={lang}', status=200)
            body = response.json
            assert body['articles']['total'] != 0

    def test_feed(self):
        for lang in DefaultLangs:
            response = self.app.get(f'/feed?pl={lang}', status=200)
            body = response.json
            assert len(body['feed']) != 0

    def test_create(self):
        for lang in DefaultLangs:
            body = {
                'article_type': 'collab',
                'locales': [{'lang': lang, 'title': 'Title'}],
            }

            document = self.post_with_auth('/articles', body).json

            document = self.app.get(f'/articles/{document["document_id"]}')
            assert lang == document.json['locales'][0]['lang']

    def test_user_preferences(self):
        user_id = self.global_userids['contributor']

        for lang in DefaultLangs:
            request_body = {
                'followed_only': True,
                'activities': [],
                'langs': [lang],
                'areas': [],
            }

            self.post_with_auth('/users/preferences', request_body)

            json = self.get_with_auth('/users/preferences').json

            assert [lang] == json['langs']

            user = self.session.get(User, user_id)
            user.ratelimit_times = 0

    def test_preferred_lang(self):
        for lang in DefaultLangs:
            body = {'lang': lang}
            self.post_with_auth('/users/update_preferred_language', body)

            user_id = self.global_userids['contributor']

            user = self.session.get(User, user_id)
            self.session.expunge(user)

            user = self.session.get(User, user_id)
            assert user.lang == lang
