from c2corg_api.models.es_sync import get_status, mark_as_updated


def test_get_status(session):
    last_update, date_now = get_status(session)
    assert last_update is not None
    assert date_now is not None


def test_mark_as_updated(session):
    _, date_now = get_status(session)
    mark_as_updated(session, date_now)

    last_update, _ = get_status(session)
    assert last_update == date_now
