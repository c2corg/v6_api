from dataclasses import dataclass

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

PREFIX = '/users/preferences'


@dataclass
class Docs:
    """The documents of the tests, built by `docs`."""

    area1: Area
    area2: Area
    contributor: User


@pytest.fixture(autouse=True)
def docs(session, user_ids) -> Docs:
    area1 = Area(
        area_type='range',
        locales=[
            DocumentLocale(lang='fr', title='France'),
            DocumentLocale(lang='de', title='Frankreich'),
        ],
    )
    area2 = Area(area_type='range', locales=[DocumentLocale(lang='fr', title='Suisse')])

    session.add_all([area1, area2])
    session.flush()

    contributor = session.get(User, user_ids['contributor'])
    contributor.feed_filter_areas.append(area1)
    contributor.feed_filter_activities = ['hiking']
    contributor.feed_filter_langs = ['fr']
    session.flush()
    return Docs(area1=area1, area2=area2, contributor=contributor)


def test_get_preferences_unauthenticated(client):
    client.get(PREFIX, status=403)


def test_get_preferences(client, docs):
    headers = auth_headers(username='contributor')
    response = client.get(PREFIX, status=200, headers=headers)
    body = response.json

    assert ['hiking'] == body['activities']
    assert ['fr'] == body['langs']
    assert body['followed_only'] is False
    areas = body['areas']
    assert 1 == len(areas)
    assert docs.area1.document_id == areas[0]['document_id']
    locale = areas[0]['locales'][0]
    # not related to the langs pref above:
    assert 'fr' == locale['lang']


def test_get_preferences_lang(client):
    """Get the preferences with parameter `lang`."""
    headers = auth_headers(username='contributor')
    response = client.get(PREFIX + '?pl=de', status=200, headers=headers)
    body = response.json

    areas = body['areas']
    locale = areas[0]['locales'][0]
    assert 'de' == locale['lang']


def test_post_preferences_unauthenticated(client):
    send_json(client, 'post', PREFIX, {}, status=403)


def test_post_preferences_invalid(client, docs):
    request_body = {
        # missing 'followed_only'
        # wrong activity
        'activities': ['hiking', 'soccer'],
        # wrong lang
        'langs': ['fr', 'xx'],
        # wrong area entry
        'areas': [{'id': docs.area2.document_id}],
    }

    headers = auth_headers(username='contributor')
    response = send_json(
        client, 'post', PREFIX, request_body, status=422, headers=headers
    )

    body = response.json

    errors = errors_of(body)

    assert get_error(errors, 'activities.1') is not None
    assert get_error(errors, 'langs.1') is not None
    assert_required(get_error(errors, 'areas.0.document_id'), 'areas.0.document_id')
    assert_required(get_error(errors, 'followed_only'), 'followed_only')


def test_post_preferences(client, session, docs):
    request_body = {
        'followed_only': True,
        'activities': ['hiking', 'skitouring'],
        'langs': ['fr', 'en'],
        'areas': [{'document_id': docs.area2.document_id}],
    }

    headers = auth_headers(username='contributor')
    send_json(client, 'post', PREFIX, request_body, status=200, headers=headers)

    session.refresh(docs.contributor)
    assert docs.contributor.feed_followed_only
    assert ['hiking', 'skitouring'] == docs.contributor.feed_filter_activities
    assert ['fr', 'en'] == docs.contributor.feed_filter_langs

    assert (
        session.query(FilterArea)
        .filter(
            FilterArea.user_id == docs.contributor.id,
            FilterArea.area_id == docs.area1.document_id,
        )
        .first()
        is None
    )
    assert (
        session.query(FilterArea)
        .filter(
            FilterArea.user_id == docs.contributor.id,
            FilterArea.area_id == docs.area2.document_id,
        )
        .first()
        is not None
    )
