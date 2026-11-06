import pytest

from c2corg_api.models.es_sync import get_status, mark_as_updated


@pytest.mark.usefixtures('client')
class TestESSyncStatus:
    def test_get_status(self, session):
        last_update, date_now = get_status(session)
        assert last_update is not None
        assert date_now is not None

    def test_mark_as_updated(self, session):
        _, date_now = get_status(session)
        mark_as_updated(session, date_now)

        last_update, _ = get_status(session)
        assert last_update == date_now
