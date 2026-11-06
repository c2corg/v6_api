from c2corg_api.tests import (
    BaseTestCase,
    assert_body_equal,
    assert_error,
    assert_errors_contain,
    assert_not_notified_es,
    assert_notified_es,
    auth_headers,
    get_error,
    get_feed_change,
    get_json_with_contributor,
    get_json_with_moderator,
    get_json_with_token,
    get_locale,
    post_json_with_contributor,
    post_json_with_token,
    sync_es_queue,
)


class BaseTestRest(BaseTestCase):
    # the functions of c2corg_api.tests, for the tests not converted yet (#2610)
    def assertErrorsContain(self, body, key, value=None):  # noqa
        assert_errors_contain(body, key, value)

    def assertBodyEqual(self, body, key, expected):  # noqa
        assert_body_equal(body, key, expected)

    def add_authorization_header(self, username=None, token=None, headers=None):
        return auth_headers(username, token, headers)

    def get_json_with_token(self, url, token, status=200):
        return get_json_with_token(self.app, url, token, status)

    def get_json_with_contributor(self, url, status=200):
        return get_json_with_contributor(self.app, url, status)

    def get_json_with_moderator(self, url, status):
        return get_json_with_moderator(self.app, url, status)

    def assertError(self, errors, name, description):  # noqa
        assert_error(errors, name, description)

    def get_error(self, errors, name):
        return get_error(errors, name)

    def post_json_with_token(self, url, token, body={}, status=200):
        return post_json_with_token(self.app, url, token, body, status)

    def post_json_with_contributor(
        self, url, body={}, status=200, username='contributor', headers={}
    ):
        return post_json_with_contributor(
            self.app, url, body, status, username, headers
        )

    def assertNotifiedEs(self):  # noqa
        assert_notified_es(self.queue_config)

    def assertNotNotifiedEs(self):  # noqa
        assert_not_notified_es(self.queue_config)

    def sync_es(self):
        sync_es_queue(self.session, self.queue_config)

    def get_locale(self, lang, locales):
        return get_locale(locales, lang)

    def get_feed_change(self, document_id, change_type=None):
        return get_feed_change(self.session, document_id, change_type)
