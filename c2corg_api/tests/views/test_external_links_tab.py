from datetime import UTC, datetime

import pytest

from c2corg_api.models import DBSession
from c2corg_api.models.link_check import LinkCheck, LinkHost
from c2corg_api.tests import auth_headers
from c2corg_api.tests.views.test_document_delete import docs  # noqa: F401
from c2corg_api.views.markdown import update_text_references

NOW = datetime(2026, 11, 27, 12, tzinfo=UTC)


def _write(session, document, text):
    locale = document.locales[0]
    locale.description = text
    session.flush()
    update_text_references([locale])
    session.flush()


def _check(session, url, status, **kwargs):
    host = url.split('/')[2]
    if DBSession.get(LinkHost, host) is None:
        session.add(LinkHost(host=host, review=kwargs.pop('host_review', None)))
    session.add(
        LinkCheck(
            url=url,
            host=host,
            status=status,
            failures=kwargs.pop('failures', 0),
            last_seen_at=NOW,
            last_checked_at=NOW,
            **kwargs,
        )
    )
    session.flush()


def _list(client, query='', username='moderator', status=200):
    return client.get(
        '/documents/external-links' + query,
        headers=auth_headers(username=username),
        status=status,
    )


def _post(client, path, body, username='moderator', status=200):
    return client.post_json(
        '/documents/external-links/' + path,
        body,
        headers=auth_headers(username=username),
        status=status,
    )


def _urls(body):
    return [link['url'] for link in body['links']]


@pytest.fixture
def links(session, docs):  # noqa: F811
    """Links of a route and a waypoint checked, and one of an outing."""
    _write(
        session,
        docs.route1,
        '[d](http://dead.example/a) [p](http://parked.example/) '
        '[o](http://ok.example/) [m](http://moved.example/old) '
        '[g](http://genuine.example/x) [t](http://trusted.example/y) '
        '[s](http://taken.example/)',
    )
    _write(session, docs.waypoint1, '[d](http://dead.example/a)')
    _write(session, docs.outing1, '[x](http://outing.example/)')
    _check(session, 'http://dead.example/a', 'dead', failures=3, error='dns')
    _check(session, 'http://parked.example/', 'parked', last_title='parked.example')
    _check(session, 'http://ok.example/', 'ok')
    _check(
        session,
        'http://moved.example/old',
        'moved',
        final_url='http://moved.example/new',
    )
    _check(session, 'http://genuine.example/x', 'offsite', review='genuine')
    _check(session, 'http://trusted.example/y', 'blocked', host_review='trusted')
    _check(session, 'http://taken.example/', 'suspect', review='taken_over')
    # an outing is not collaborative: never listed
    _check(session, 'http://outing.example/', 'dead')
    return docs


def test_list_needing_a_look(client, links):
    body = _list(client).json
    # by host; a link taken over stays until removed
    assert _urls(body) == [
        'http://dead.example/a',
        'http://parked.example/',
        'http://taken.example/',
    ]
    assert body['total'] == 3
    assert body['counts'] == {
        'dead': 1,
        'failing': 0,
        'parked': 1,
        'suspect': 1,
        'offsite': 0,
        'moved': 1,
        'blocked': 0,
        'ok': 1,
        'unchecked': 0,
    }
    dead = body['links'][0]
    assert (dead['status'], dead['error'], dead['failures']) == ('dead', 'dns', 3)
    assert dead['documents_count'] == 2
    assert sorted(d['document_id'] for d in dead['documents']) == sorted(
        [links.route1.document_id, links.waypoint1.document_id]
    )
    assert {'title', 'title_prefix', 'langs', 'document_type'} <= set(
        dead['documents'][0]
    )


def test_list_filters(client, links):
    assert _urls(_list(client, '?status=moved,ok').json) == [
        'http://moved.example/old',
        'http://ok.example/',
    ]
    assert _urls(_list(client, '?host=Dead.example').json) == ['http://dead.example/a']
    reviewed = _list(client, '?reviewed=true&status=offsite,blocked').json
    assert _urls(reviewed) == ['http://genuine.example/x', 'http://trusted.example/y']
    assert reviewed['links'][1]['host_review'] == 'trusted'
    assert _urls(_list(client, '?offset=1&limit=1').json) == ['http://parked.example/']


def test_review_link(client, session, links, user_ids):
    url = 'http://parked.example/'
    assert _post(client, 'review', {'url': url, 'review': 'genuine'}).json == {
        'url': url,
        'review': 'genuine',
    }
    session.expire_all()
    check = session.get(LinkCheck, url)
    assert (check.review, check.reviewed_by) == ('genuine', user_ids['moderator'])
    # genuine until its title changes completely: from the title seen now
    assert check.first_title == 'parked.example'
    assert url not in _urls(_list(client).json)

    _post(client, 'review', {'url': url})
    session.expire_all()
    check = session.get(LinkCheck, url)
    assert (check.review, check.reviewed_by, check.reviewed_at) == (None, None, None)


def test_review_host_and_recheck(client, session, links):
    _post(client, 'review-host', {'host': 'Dead.example', 'review': 'trusted'})
    assert 'http://dead.example/a' not in _urls(_list(client).json)
    _post(client, 'review-host', {'host': 'dead.example'})
    assert 'http://dead.example/a' in _urls(_list(client).json)

    before = datetime.now(UTC)
    _post(client, 'recheck', {'url': 'http://dead.example/a'})
    session.expire_all()
    assert session.get(LinkCheck, 'http://dead.example/a').next_check_at >= before


def test_review_refused(client, links):
    _post(client, 'review', {'url': 'http://unknown.example/'}, status=400)
    _post(client, 'review-host', {'host': 'unknown.example'}, status=400)
    _post(client, 'recheck', {'url': 'http://unknown.example/'}, status=400)
    _post(client, 'review', {'url': 'http://ok.example/', 'review': 'nice'}, status=422)
    _post(
        client, 'review-host', {'host': 'ok.example', 'review': 'genuine'}, status=422
    )


def test_reserved_to_the_moderators(client, links):
    _list(client, username='contributor', status=403)
    client.get('/documents/external-links', status=403)
    _post(
        client,
        'review',
        {'url': 'http://ok.example/', 'review': 'genuine'},
        username='contributor',
        status=403,
    )
