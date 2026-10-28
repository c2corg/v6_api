from unittest.mock import Mock, patch

from c2corg_api.tests.contract import check_snapshot, contract
from c2corg_api.tests.contract.test_writes import WriteContractTest, writable

IMAGE_BACKEND = 'c2corg_api.views.image.requests.post'


class TestXreportWrites(WriteContractTest):
    @contract(('PUT', '/xreports/{id}'))
    def test_update_by_another_user(self):
        # only its author, its associated users and the moderators
        def change(document):
            document['locales'][0]['title'] += ' (2)'

        response = self.update('xreports', change, user='contributor2', status=403)
        check_snapshot('xreports_update_forbidden', response)
        assert response.json['errors'][0]['description'] == (
            'No permission to change this xreport'
        )


class TestImageWrites(WriteContractTest):
    def image_type(self, image_type, user='contributor', status=200):
        def change(document):
            document['image_type'] = image_type

        return self.update('images', change, user=user, status=status)

    @contract(('PUT', '/images/{id}'))
    def test_type_of_a_collaborative_image(self):
        response = self.image_type('personal', status=400)
        check_snapshot('images_update_type', response)
        assert response.json['errors'][0]['description'] == (
            'Image type cannot be changed for collaborative images'
        )
        response = self.image_type('copyright', status=403)
        check_snapshot('images_update_copyright', response)
        assert response.json['errors'][0]['description'] == (
            'No permission to change to copyright type'
        )

    @contract(('POST', '/images'), ('PUT', '/images/{id}'))
    def test_personal_image_of_another_user(self):
        document = writable(self.get(self.url('images')).json, keep_ids=False)
        for locale in document['locales']:
            locale.pop('version', None)
        document.update(filename='personal.jpg', image_type='personal')
        with patch(IMAGE_BACKEND, return_value=Mock(status_code=200)):
            image_id = self.post('/images', document, user='contributor').json[
                'document_id'
            ]
        document = writable(self.get(f'/images/{image_id}').json)
        document['locales'][0]['title'] = 'Not my view'
        body = {'message': 'contract test', 'document': document}
        response = self.put(
            f'/images/{image_id}', body, user='contributor2', status=403
        )
        check_snapshot('images_update_forbidden', response)
        assert response.json['errors'][0]['description'] == (
            'No permission to change this image'
        )

    @contract(('PUT', '/images/{id}'))
    def test_unknown_image(self):
        document = writable(self.get(self.url('images')).json)
        document['document_id'] = 9999999
        body = {'message': 'contract test', 'document': document}
        response = self.put('/images/9999999', body, user='contributor', status=404)
        check_snapshot('images_update_unknown', response)


class TestProfileWrites(WriteContractTest):
    @contract(('PUT', '/profiles/{id}'))
    def test_profile_of_another_user(self):
        def change(document):
            document['locales'][0]['description'] = 'Not my profile'

        response = self.update('profiles', change, user='contributor2', status=403)
        check_snapshot('profiles_update_forbidden', response)
        assert response.json['errors'][0]['description'] == (
            'No permission to change this user profile'
        )
        # a moderator changes every profile
        response = self.update('profiles', change, user='moderator')
        check_snapshot('profiles_update_by_moderator', response)
