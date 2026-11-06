import pytest

from c2corg_api.models.feed import DocumentChange
from c2corg_api.scripts.es.sync import sync_es
from c2corg_api.tests import BaseTestCase, auth_headers, errors_of, get_error


class BaseTestRest(BaseTestCase):
    def assertErrorsContain(self, body, key, value=None):  # noqa
        for error in errors_of(body):
            if error.get('name') == key:
                if value is not None:
                    assert error.get('description') == value
                return
        pytest.fail(str(body) + ' does not contain ' + key)

    def assertBodyEqual(self, body, key, expected):  # noqa
        assert body.get(key) == expected

    def add_authorization_header(self, username=None, token=None, headers=None):
        return auth_headers(username, token, headers)

    def get_json_with_token(self, url, token, status=200):
        headers = self.add_authorization_header(token=token)
        return self.app.get(url, headers=headers, status=status).json

    def get_json_with_contributor(self, url, status=200):
        headers = self.add_authorization_header(username='contributor')
        return self.app.get(url, headers=headers, status=status).json

    def get_json_with_moderator(self, url, status):
        headers = self.add_authorization_header(username='moderator')
        return self.app.get(url, headers=headers, status=status).json

    def assertError(self, errors, name, description):  # noqa
        for error in errors:
            if description == error.get('description') and name == error.get('name'):
                return
        pytest.fail(f'no error ({name}, {description}) in {errors}')

    def get_error(self, errors, name):
        return get_error(errors, name)

    def post_json_with_token(self, url, token, body={}, status=200):
        headers = self.add_authorization_header(token=token)
        r = self.app_post_json(url, body, headers=headers, status=status)
        return r.json

    def post_json_with_contributor(
        self, url, body={}, status=200, username='contributor', headers={}
    ):
        headers = self.add_authorization_header(username=username, headers=headers)
        r = self.app_post_json(url, body, headers=headers, status=status)
        return r.json

    def assertNotifiedEs(self):  # noqa
        queue = self.queue_config.queue(self.queue_config.connection)
        assert queue.get() is not None, 'no sync. notification sent for ES'

    def assertNotNotifiedEs(self):  # noqa
        queue = self.queue_config.queue(self.queue_config.connection)
        assert queue.get() is None, 'unexpected sync. notification sent for ES'

    def sync_es(self):
        self.assertNotifiedEs()
        sync_es(self.session)

    def get_locale(self, lang, locales):
        return next(filter(lambda locale: locale['lang'] == lang, locales), None)

    def get_feed_change(self, document_id, change_type=None):
        q = self.session.query(DocumentChange).filter(
            DocumentChange.document_id == document_id
        )

        if change_type:
            q = q.filter(DocumentChange.change_type == change_type)

        return q.first()
