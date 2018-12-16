from c2corg_api.tests.views import BaseTestRest


class TestCookerRest(BaseTestRest):
    def setUp(self):  # noqa
        super(TestCookerRest, self).setUp()

    def test_get(self):
        body = {
            "lang": "fr",
            "oui": "**coucou** *italic*"
        }
        self.app_post_json('/cooker', body, status=200)
