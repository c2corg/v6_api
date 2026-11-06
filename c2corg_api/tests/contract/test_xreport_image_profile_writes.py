from unittest.mock import Mock, patch

import pytest

from c2corg_api.tests.contract import check_snapshot, contract
from c2corg_api.tests.contract.test_writes import writable

IMAGE_BACKEND = 'c2corg_api.views.image.requests.post'


@pytest.mark.usefixtures('documents')
class TestXreportWrites:
    @contract(('PUT', '/xreports/{id}'))
    def test_update_by_another_user(self, documents):
        # only its author, its associated users and the moderators
        def change(document):
            document['locales'][0]['title'] += ' (2)'

        response = documents.update(
            'xreports',
            change,
            user='contributor2',
            status=403,
        )
        check_snapshot('xreports_update_forbidden', response)
        assert response.json['errors'][0]['description'] == (
            'No permission to change this xreport'
        )


def image_type(documents, image_type, user='contributor', status=200):
    def change(document):
        document['image_type'] = image_type

    return documents.update('images', change, user=user, status=status)


@pytest.mark.usefixtures('documents')
class TestImageWrites:
    @contract(('PUT', '/images/{id}'))
    def test_type_of_a_collaborative_image(self, documents):
        response = image_type(documents, 'personal', status=400)
        check_snapshot('images_update_type', response)
        assert response.json['errors'][0]['description'] == (
            'Image type cannot be changed for collaborative images'
        )
        response = image_type(documents, 'copyright', status=403)
        check_snapshot('images_update_copyright', response)
        assert response.json['errors'][0]['description'] == (
            'No permission to change to copyright type'
        )

    @contract(('POST', '/images'), ('PUT', '/images/{id}'))
    def test_personal_image_of_another_user(self, browser, documents):
        document = writable(
            browser.get(documents.url('images')).json,
            keep_ids=False,
        )
        for locale in document['locales']:
            locale.pop('version', None)
        document.update(filename='personal.jpg', image_type='personal')
        with patch(IMAGE_BACKEND, return_value=Mock(status_code=200)):
            image_id = browser.post('/images', document, user='contributor').json[
                'document_id'
            ]
        document = writable(browser.get(f'/images/{image_id}').json)
        document['locales'][0]['title'] = 'Not my view'
        body = {'message': 'contract test', 'document': document}
        response = browser.put(
            f'/images/{image_id}',
            body,
            user='contributor2',
            status=403,
        )
        check_snapshot('images_update_forbidden', response)
        assert response.json['errors'][0]['description'] == (
            'No permission to change this image'
        )

    @contract(('PUT', '/images/{id}'))
    def test_unknown_image(self, browser, documents):
        document = writable(browser.get(documents.url('images')).json)
        document['document_id'] = 9999999
        body = {'message': 'contract test', 'document': document}
        response = browser.put('/images/9999999', body, user='contributor', status=404)
        check_snapshot('images_update_unknown', response)


@pytest.mark.usefixtures('documents')
class TestProfileWrites:
    @contract(('PUT', '/profiles/{id}'))
    def test_profile_of_another_user(self, documents):
        def change(document):
            document['locales'][0]['description'] = 'Not my profile'

        response = documents.update(
            'profiles',
            change,
            user='contributor2',
            status=403,
        )
        check_snapshot('profiles_update_forbidden', response)
        assert response.json['errors'][0]['description'] == (
            'No permission to change this user profile'
        )
        # a moderator changes every profile
        response = documents.update('profiles', change, user='moderator')
        check_snapshot('profiles_update_by_moderator', response)
