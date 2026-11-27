from datetime import UTC, datetime, timedelta

import pytest

from c2corg_api.linkcheck import checker, rel
from c2corg_api.linkcheck import classify as c
from c2corg_api.linkcheck import fetch as f
from c2corg_api.models.cache_version import CacheVersion
from c2corg_api.models.link_check import LinkCheck, LinkHost
from c2corg_api.tests import auth_headers
from c2corg_api.tests.views.test_document_delete import docs  # noqa: F401
from c2corg_api.views.markdown import cook, update_text_references

NOW = datetime(2026, 11, 27, 12, tzinfo=UTC)


def _check(status='ok', review=None, last_ok_at=NOW, **kwargs):
    return LinkCheck(
        url='http://a.example/',
        host='a.example',
        status=status,
        failures=0,
        last_seen_at=NOW,
        review=review,
        last_ok_at=last_ok_at,
        **kwargs,
    )


@pytest.mark.parametrize(
    ('check', 'host_review', 'credited'),
    [
        (_check(), None, True),
        (_check('moved'), None, True),
        # fine, but too long ago
        (_check(last_ok_at=NOW - timedelta(days=91)), None, False),
        (_check('unchecked', last_ok_at=None), None, False),
        (_check('offsite', last_ok_at=None), None, False),
        (_check('blocked', last_ok_at=None), None, False),
        # reviewed genuine, a trusted site: credited, unless gone or doubtful
        (_check('offsite', 'genuine', last_ok_at=None), None, True),
        (_check('blocked', last_ok_at=None), 'trusted', True),
        (_check('unchecked', last_ok_at=None), 'trusted', True),
        (_check('dead', 'genuine'), 'trusted', False),
        (_check('failing'), 'trusted', False),
        (_check('parked'), None, False),
        (_check('suspect', 'genuine'), None, False),
        # taken over: never
        (_check('ok', 'taken_over'), 'trusted', False),
        (None, 'trusted', True),
        (None, None, False),
    ],
)
def test_is_credited(check, host_review, credited):
    assert rel.is_credited(check, host_review, NOW) is credited


def test_text_urls():
    texts = [
        'voir [le refuge](http://refuge.example/a?b=1&c=2), '
        '<https://meteo.example/x> et http://bare.example/y.',
        None,
    ]
    assert rel.text_urls(texts) == {
        'http://refuge.example/a?b=1&c=2',
        'https://meteo.example/x',
        'http://bare.example/y',
    }


def _add(session, url, host_review=None, **kwargs):
    host = url.split('/')[2]
    if session.get(LinkHost, host) is None:
        session.add(LinkHost(host=host, review=host_review))
    session.add(
        LinkCheck(
            url=url,
            host=host,
            status=kwargs.pop('status', 'ok'),
            failures=0,
            last_seen_at=datetime.now(UTC),
            last_ok_at=kwargs.pop('last_ok_at', datetime.now(UTC)),
            **kwargs,
        )
    )
    session.flush()


def test_cook_credits_genuine_links(session):
    _add(session, 'http://fine.example/')
    _add(session, 'http://dead.example/', status='dead')
    _add(
        session,
        'http://trusted.example/robots',
        host_review='trusted',
        status='blocked',
    )
    cooked = cook(
        {
            'lang': 'fr',
            'description': '[f](http://fine.example/) [d](http://dead.example/) '
            '[t](http://trusted.example/robots) [n](http://never.example/)',
        }
    )['description']
    assert '<a href="http://fine.example/">f</a>' in cooked
    assert '<a href="http://trusted.example/robots">t</a>' in cooked
    assert '<a href="http://dead.example/" rel="nofollow ugc">d</a>' in cooked
    assert '<a href="http://never.example/" rel="nofollow ugc">n</a>' in cooked


def _write(session, document, text):
    locale = document.locales[0]
    locale.description = text
    session.flush()
    update_text_references([locale])
    session.flush()


def _version(session, document):
    session.expire_all()
    return session.get(CacheVersion, document.document_id).version


def test_check_changing_the_credit_renders_again(session, docs, monkeypatch):  # noqa: F811
    _write(session, docs.route1, '[a](http://a.example/x)')
    _add(session, 'http://a.example/x', status='unchecked', last_ok_at=None)
    check = session.get(LinkCheck, 'http://a.example/x')
    host = session.get(LinkHost, 'a.example')
    host.robots_fetched_at = datetime.now(UTC)
    page = f.Answer(url=check.url, urls=[check.url], http_status=200, title='Topo')
    monkeypatch.setattr(checker, 'fetch', lambda url, read_body=True: page)
    before = _version(session, docs.route1)

    # unchecked -> ok: credited, the route rendered again
    checker.check_link(session, check, host, datetime.now(UTC))
    assert check.status == c.OK
    assert _version(session, docs.route1) == before + 1

    # ok again: no change, no new rendering
    check = session.get(LinkCheck, 'http://a.example/x')
    checker.check_link(session, check, host, datetime.now(UTC))
    assert _version(session, docs.route1) == before + 1

    # failing: no longer credited
    gone = f.Answer(url=check.url, urls=[check.url], http_status=404)
    monkeypatch.setattr(checker, 'fetch', lambda url, read_body=True: gone)
    check = session.get(LinkCheck, 'http://a.example/x')
    checker.check_link(session, check, host, datetime.now(UTC))
    assert _version(session, docs.route1) == before + 2


def test_reviews_render_again(client, session, docs):  # noqa: F811
    _write(session, docs.route1, '[a](http://a.example/x) [b](http://a.example/y)')
    _add(session, 'http://a.example/x', status='offsite', last_ok_at=None)
    _add(session, 'http://a.example/y', status='blocked', last_ok_at=None)
    before = _version(session, docs.route1)

    def post(path, body):
        client.post_json(
            '/documents/external-links/' + path,
            body,
            headers=auth_headers(username='moderator'),
            status=200,
        )

    post('review', {'url': 'http://a.example/x', 'review': 'genuine'})
    assert _version(session, docs.route1) == before + 1
    # taken over: no longer credited
    post('review', {'url': 'http://a.example/x', 'review': 'taken_over'})
    assert _version(session, docs.route1) == before + 2
    # trusting the site credits its other link (not the one taken over)
    post('review-host', {'host': 'a.example', 'review': 'trusted'})
    assert _version(session, docs.route1) == before + 3
    cooked = cook({'lang': 'fr', 'description': docs.route1.locales[0].description})
    assert '<a href="http://a.example/y">b</a>' in cooked['description']
    assert 'href="http://a.example/x" rel="nofollow ugc"' in cooked['description']
