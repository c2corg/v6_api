from c2corg_api.tests.views import BaseTestRest


class TestCookerRest(BaseTestRest):
    def setUp(self):  # noqa
        super(TestCookerRest, self).setUp()

    def test_get(self):
        markdowns = {
            "lang": "fr",
            "description": "**strong emphasis** and *emphasis*"
        }
        response = self.app_post_json('/cooker', markdowns, status=200)

        htmls = response.json

        # lang is not a markdown field, it must be untouched
        self.assertEqual(markdowns['lang'], htmls['lang'])
        self.assertNotEqual(markdowns['description'], htmls['description'])
