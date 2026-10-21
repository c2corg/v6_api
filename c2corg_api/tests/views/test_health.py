from c2corg_api.tests.views import BaseTestRest


class TestHealthRest(BaseTestRest):
    def setUp(self):  # noqa
        super().setUp()

    def test_get(self):
        r = self.app.get('/health', status=200)

        data = r.json

        self.assertEqual(data['es'], 'ok')
        self.assertEqual(data['redis'], 'ok')
