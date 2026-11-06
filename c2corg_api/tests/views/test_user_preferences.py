import pytest

from c2corg_api.models.area import Area
from c2corg_api.models.document import DocumentLocale
from c2corg_api.models.feed import FilterArea
from c2corg_api.models.user import User
from c2corg_api.tests import (
    assert_required,
    auth_headers,
    errors_of,
    get_error,
    send_json,
)


class TestUserFilterPreferencesRest:
    @pytest.fixture(autouse=True)
    def _setup_test_user_filter_preferences_rest(self, client, session, user_ids):
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

        session.add_all([self.area1, self.area2])
        session.flush()

        self.contributor = session.get(User, user_ids['contributor'])
        self.contributor.feed_filter_areas.append(self.area1)
        self.contributor.feed_filter_activities = ['hiking']
        self.contributor.feed_filter_langs = ['fr']
        session.flush()

    def test_get_preferences_unauthenticated(self, client):
        client.get(self._prefix, status=403)

    def test_get_preferences(self, client):
        headers = auth_headers(username='contributor')
        response = client.get(self._prefix, status=200, headers=headers)
        body = response.json

        assert ['hiking'] == body['activities']
        assert ['fr'] == body['langs']
        assert body['followed_only'] is False
        areas = body['areas']
        assert 1 == len(areas)
        assert self.area1.document_id == areas[0]['document_id']
        locale = areas[0]['locales'][0]
        # not related to the langs pref above:
        assert 'fr' == locale['lang']

    def test_get_preferences_lang(self, client):
        """Get the preferences with parameter `lang`."""
        headers = auth_headers(username='contributor')
        response = client.get(self._prefix + '?pl=de', status=200, headers=headers)
        body = response.json

        areas = body['areas']
        locale = areas[0]['locales'][0]
        assert 'de' == locale['lang']

    def test_post_preferences_unauthenticated(self, client):
        send_json(client, 'post', self._prefix, {}, status=403)

    def test_post_preferences_invalid(self, client):
        request_body = {
            # missing 'followed_only'
            # wrong activity
            'activities': ['hiking', 'soccer'],
            # wrong lang
            'langs': ['fr', 'xx'],
            # wrong area entry
            'areas': [{'id': self.area2.document_id}],
        }

        headers = auth_headers(username='contributor')
        response = send_json(
            client, 'post', self._prefix, request_body, status=422, headers=headers
        )

        body = response.json

        errors = errors_of(body)

        assert get_error(errors, 'activities.1') is not None
        assert get_error(errors, 'langs.1') is not None
        assert_required(get_error(errors, 'areas.0.document_id'), 'areas.0.document_id')
        assert_required(get_error(errors, 'followed_only'), 'followed_only')

    def test_post_preferences(self, client, session):
        request_body = {
            'followed_only': True,
            'activities': ['hiking', 'skitouring'],
            'langs': ['fr', 'en'],
            'areas': [{'document_id': self.area2.document_id}],
        }

        headers = auth_headers(username='contributor')
        send_json(
            client, 'post', self._prefix, request_body, status=200, headers=headers
        )

        session.refresh(self.contributor)
        assert self.contributor.feed_followed_only
        assert ['hiking', 'skitouring'] == self.contributor.feed_filter_activities
        assert ['fr', 'en'] == self.contributor.feed_filter_langs

        assert (
            session.query(FilterArea)
            .filter(
                FilterArea.user_id == self.contributor.id,
                FilterArea.area_id == self.area1.document_id,
            )
            .first()
            is None
        )
        assert (
            session.query(FilterArea)
            .filter(
                FilterArea.user_id == self.contributor.id,
                FilterArea.area_id == self.area2.document_id,
            )
            .first()
            is not None
        )
