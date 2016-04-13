from c2corg_api.models.es_sync import get_status, mark_as_updated

from c2corg_api.tests import BaseTestCase


class TestESSyncStatus(BaseTestCase):

    def test_get_status(self):
        last_update, date_now = get_status(self.session)
        self.assertIsNotNone(last_update)
        self.assertIsNotNone(date_now)

    def test_mark_as_updated(self):
        _, date_now = get_status(self.session)
        mark_as_updated(self.session, date_now)

        last_update, _ = get_status(self.session)
        self.assertEqual(last_update, date_now)
