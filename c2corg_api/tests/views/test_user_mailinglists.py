import pytest

from c2corg_api.models.common.attributes import mailinglists
from c2corg_api.models.mailinglist import Mailinglist
from c2corg_api.models.user import User
from c2corg_api.tests import auth_headers, get_error, send_json

PREFIX = '/users/mailinglists'


@pytest.fixture(autouse=True)
def contributor(session, user_ids):
    """Return the contributor, subscribed to two mailing lists."""
    contributor = session.get(User, user_ids['contributor'])
    ml1 = Mailinglist(
        listname='meteofrance-74',
        email=contributor.email,
        user_id=contributor.id,
        user=contributor,
    )
    ml2 = Mailinglist(
        listname='avalanche.en',
        email=contributor.email,
        user_id=contributor.id,
        user=contributor,
    )
    session.add_all([ml1, ml2])
    session.flush()
    return contributor


def test_get_mailinglists_unauthenticated(client):
    client.get(PREFIX, status=403)


def test_get_mailinglists(client):
    headers = auth_headers(username='contributor')
    response = client.get(PREFIX, status=200, headers=headers)
    body = response.json

    assert len(body) == len(mailinglists)
    for ml in mailinglists:
        assert ml in body
        if ml in ['meteofrance-74', 'avalanche.en']:
            assert body[ml]
        else:
            assert not body[ml]


def test_post_mailinglists_unauthenticated(client):
    send_json(client, 'post', PREFIX, {}, status=403)


def test_post_mailinglists_invalid(client):
    request_body = {'wrong_mailinglist_name': True, 'avalanche': 'incorrect_value'}

    headers = auth_headers(username='contributor')
    response = send_json(
        client, 'post', PREFIX, request_body, status=400, headers=headers
    )

    body = response.json
    assert body.get('status') == 'error'
    errors = body.get('errors')
    assert get_error(errors, 'wrong_mailinglist_name') is not None
    assert get_error(errors, 'avalanche') is not None


def test_post_mailinglists(client, session, contributor):
    request_body = {'meteofrance-66': True, 'meteofrance-74': False}

    headers = auth_headers(username='contributor')
    send_json(client, 'post', PREFIX, request_body, status=200, headers=headers)

    mls = (
        session.query(Mailinglist.listname)
        .filter(Mailinglist.email == contributor.email)
        .all()
    )
    subscribed_mailinglists = [list[0] for list in mls]
    assert len(subscribed_mailinglists) == 2
    assert 'meteofrance-66' in subscribed_mailinglists
    assert 'avalanche.en' in subscribed_mailinglists
    assert 'meteofrance-74' not in subscribed_mailinglists
