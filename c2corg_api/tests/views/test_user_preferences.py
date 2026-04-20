from c2corg_api.models.area import Area
from c2corg_api.models.document import DocumentLocale
from c2corg_api.models.feed import FilterArea
from c2corg_api.models.user import User
from c2corg_api.tests.views import BaseTestRest


class TestUserFilterPreferencesRest(BaseTestRest):
    def setUp(self):  # noqa
        super(TestUserFilterPreferencesRest, self).setUp()
        self._prefix = '/users/preferences'

        self.area1 = Area(
            area_type='range',
            locales=[
                DocumentLocale(lang='fr', title='France'),
                DocumentLocale(lang='de', title='Frankreich'),
            ],
        )
        self.area2 = Area(
            area_type='range', locales=[DocumentLocale(lang='fr', title='Suisse')]
        )

        self.session.add_all([self.area1, self.area2])
        self.session.flush()

        self.contributor = self.session.get(User, self.global_userids['contributor'])
        self.contributor.feed_filter_areas.append(self.area1)
        self.contributor.feed_filter_activities = ['hiking']
        self.contributor.feed_filter_langs = ['fr']
        self.session.flush()

    def test_get_preferences_unauthenticated(self):
        self.app.get(self._prefix, status=403)

    def test_get_preferences(self):
        headers = self.add_authorization_header(username='contributor')
        response = self.app.get(self._prefix, status=200, headers=headers)
        body = response.json

        assert ['hiking'] == body['activities']
        assert ['fr'] == body['langs']
        assert False is body['followed_only']
        areas = body['areas']
        assert 1 == len(areas)
        assert self.area1.document_id == areas[0]['document_id']
        locale = areas[0]['locales'][0]
        # not related to the langs pref above:
        assert 'fr' == locale['lang']

    def test_get_preferences_lang(self):
        """Get the preferences with parameter `lang`."""
        headers = self.add_authorization_header(username='contributor')
        response = self.app.get(self._prefix + '?pl=de', status=200, headers=headers)
        body = response.json

        areas = body['areas']
        locale = areas[0]['locales'][0]
        assert 'de' == locale['lang']

    def test_post_preferences_unauthenticated(self):
        self.app_post_json(self._prefix, {}, status=403)

    def test_post_preferences_invalid(self):
        request_body = {
            # missing 'followed_only'
            # wrong activity
            'activities': ['hiking', 'soccer'],
            # wrong lang
            'langs': ['fr', 'xx'],
            # wrong area entry
            'areas': [{'id': self.area2.document_id}],
        }

        headers = self.add_authorization_header(username='contributor')
        response = self.app_post_json(
            self._prefix, request_body, status=400, headers=headers
        )

        body = response.json
        assert body.get('status') == 'error'
        errors = body.get('errors')

        assert self.get_error(errors, 'activities') is not None
        assert self.get_error(errors, 'langs') is not None
        assert self.get_error(errors, 'areas.0.document_id') is not None
        assert self.get_error(errors, 'followed_only') is not None

    def test_post_preferences(self):
        request_body = {
            'followed_only': True,
            'activities': ['hiking', 'skitouring'],
            'langs': ['fr', 'en'],
            'areas': [{'document_id': self.area2.document_id}],
        }

        headers = self.add_authorization_header(username='contributor')
        self.app_post_json(self._prefix, request_body, status=200, headers=headers)

        self.session.refresh(self.contributor)
        assert self.contributor.feed_followed_only
        assert ['hiking', 'skitouring'] == self.contributor.feed_filter_activities
        assert ['fr', 'en'] == self.contributor.feed_filter_langs

        assert (
            self.session.query(FilterArea)
            .filter(
                FilterArea.user_id == self.contributor.id,
                FilterArea.area_id == self.area1.document_id,
            )
            .first()
            is None
        )
        assert (
            self.session.query(FilterArea)
            .filter(
                FilterArea.user_id == self.contributor.id,
                FilterArea.area_id == self.area2.document_id,
            )
            .first()
            is not None
        )
