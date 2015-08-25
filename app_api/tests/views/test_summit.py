import json

from .. import BaseTestCase


class TestSummitRest(BaseTestCase):

    def setUp(self):  # noqa
        BaseTestCase.setUp(self)
        self._add_test_data()
        # self.config.scan('app_api.views.summit')

    def test_get(self):
        response = self.app.get('/summits/' + str(self.summit.id))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, 'application/json')

        body = json.loads(response.body)
        self.assertEqual(body.get('id'), self.summit.id)

    def _add_test_data(self):
        from app_api.models.summit import Summit
        self.summit = \
            Summit(lon=6.4, lat=49.3, elevation=260.3, is_latest_version=True)
        self.session.add(self.summit)
        self.session.flush()
