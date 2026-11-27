import ipaddress
import socket
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from c2corg_api.linkcheck import checker
from c2corg_api.linkcheck import classify as c
from c2corg_api.linkcheck import fetch as f
from c2corg_api.models import DBSession
from c2corg_api.models.link_check import (
    BLOCKED,
    DEAD,
    FAILING,
    GENUINE,
    OK,
    SUSPECT,
    UNCHECKED,
    LinkCheck,
    LinkHost,
)
from c2corg_api.tests.views.test_document_delete import docs  # noqa: F401
from c2corg_api.views.markdown import update_text_references

NOW = datetime(2026, 11, 27, 12, tzinfo=UTC)

# the addresses of the hosts of the tests
ADDRESSES = {
    'example.com': '93.184.215.14',
    'www.example.com': '93.184.215.14',
    'other.example': '93.184.215.15',
    'parked.example': '93.184.215.16',
    'redis': '10.0.0.5',
    'evil.example': '127.0.0.1',
    'metadata.example': '169.254.169.254',
    'mixed.example': ('93.184.215.17', '192.168.1.2'),
}


class FakeResponse:
    def __init__(self, status, headers=None, body=b''):
        self.status = status
        self.headers = headers or {}
        self.body = body

    def stream(self, size):
        yield self.body

    def release_conn(self):
        pass

    def drain_conn(self):
        pass


@pytest.fixture
def network(monkeypatch):
    """A fake DNS and web: {url: FakeResponse}; the safety checks are real."""
    pages = {}

    def getaddrinfo(host, port, type=0, **kwargs):
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            family = socket.AF_INET if address.version == 4 else socket.AF_INET6
            return [(family, socket.SOCK_STREAM, 6, '', (host, port))]
        if host not in ADDRESSES:
            raise socket.gaierror(socket.EAI_NONAME, 'Name or service not known')
        addresses = ADDRESSES[host]
        if isinstance(addresses, str):
            addresses = (addresses,)
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', (a, port)) for a in addresses
        ]

    def _open(scheme, host, port, path, deadline):
        f.resolve_public(host, port)
        url = f'{scheme}://{host}{path}'
        if url not in pages:
            return FakeResponse(404, {'Content-Type': 'text/html'})
        return pages[url]

    monkeypatch.setattr(socket, 'getaddrinfo', getaddrinfo)
    monkeypatch.setattr(f, '_open', _open)
    return pages


def _page(title, body='', status=200):
    html = f'<html><head><title>{title}</title></head><body>{body}</body></html>'
    return FakeResponse(
        status, {'Content-Type': 'text/html; charset=utf-8'}, html.encode()
    )


def _redirect(location, status=301):
    return FakeResponse(status, {'Location': location})


@pytest.mark.parametrize(
    ('url', 'error'),
    [
        ('http://redis/', f.PRIVATE),
        ('http://evil.example/', f.PRIVATE),
        ('http://metadata.example/latest/', f.PRIVATE),
        # one private address is enough
        ('http://mixed.example/', f.PRIVATE),
        ('http://127.0.0.1/', f.PRIVATE),
        ('http://[::1]/', f.PRIVATE),
        ('http://example.com:6379/', f.PORT),
        ('http://nowhere.example/', f.DNS),
    ],
)
def test_fetch_refuses(network, url, error):
    assert f.fetch(url).error == error


def test_fetch_checks_each_redirection(network):
    network['http://example.com/a'] = _redirect('https://example.com/b')
    network['https://example.com/b'] = _redirect('http://redis/')
    answer = f.fetch('http://example.com/a')
    assert answer.error == f.PRIVATE
    assert answer.urls == [
        'http://example.com/a',
        'https://example.com/b',
        'http://redis/',
    ]

    network['https://example.com/b'] = _redirect('gopher://example.com/')
    assert f.fetch('http://example.com/a').error == f.SCHEME


def test_fetch_follows_redirections(network):
    network['http://example.com/a'] = _redirect('/b')
    network['http://example.com/b'] = _page('Topo &amp; refuge  ')
    answer = f.fetch('http://example.com/a')
    assert (answer.http_status, answer.final_url, answer.title) == (
        200,
        'http://example.com/b',
        'Topo & refuge',
    )

    network['http://example.com/loop'] = _redirect('/loop')
    assert f.fetch('http://example.com/loop').error == f.TOO_MANY_REDIRECTS


def _answer(url, status=200, title=None, text='', final_url=None, error=None):
    answer = f.Answer(url=url, http_status=status, title=title, text=text, error=error)
    answer.urls = [url] if final_url is None else [url, final_url]
    return answer


@pytest.mark.parametrize(
    ('answer', 'reference', 'outcome'),
    [
        (_answer('http://a.example/x', title='Topo'), None, c.OK),
        # http to https, www., a final slash: the same page
        (
            _answer('http://a.example/x', final_url='https://www.a.example/x/'),
            None,
            c.OK,
        ),
        (_answer('http://a.example/x', final_url='http://a.example/y'), None, c.MOVED),
        (_answer('http://a.fr/x', final_url='https://www.a.com/x'), None, c.MOVED),
        (_answer('http://a.example/x', final_url='http://b.example/'), None, c.OFFSITE),
        # two blogs of a blog platform are two sites
        (
            _answer('http://a.blogspot.com/', final_url='http://b.blogspot.com/'),
            None,
            c.OFFSITE,
        ),
        (
            _answer('http://x.blogspot.fr/a', final_url='http://x.blogspot.com/a'),
            None,
            c.MOVED,
        ),
        (_answer('https://bit.ly/x', final_url='https://topo.example/'), None, c.OK),
        (_answer('http://a.example/', text='This domain is for sale!'), None, c.PARKED),
        (
            _answer('http://a.example/', text='<a href="https://dan.com/x">'),
            None,
            c.PARKED,
        ),
        (_answer('http://a.example/', text='jordan.com'), None, c.OK),
        (
            _answer('http://a.example/', title='Best online casino 2026'),
            None,
            c.SUSPECT,
        ),
        (_answer('http://a.example/', title='Sexten Dolomiten'), None, c.OK),
        (
            _answer('http://a.example/', title='Achat rapide'),
            'Topo du Vercors',
            c.SUSPECT,
        ),
        (
            _answer('http://a.example/', title='Le Vercors, topo'),
            'Topo du Vercors',
            c.OK,
        ),
        (_answer('http://a.example/', title=None), 'Topo du Vercors', c.OK),
        (_answer('http://a.example/', title='Page introuvable'), None, c.FAILURE),
        (_answer('http://a.example/', status=404), None, c.FAILURE),
        (_answer('http://a.example/', status=410), None, c.FAILURE),
        (_answer('http://a.example/', status=None, error=f.DNS), None, c.FAILURE),
        (_answer('http://a.example/', status=None, error=f.TLS), None, c.FAILURE),
        (_answer('http://a.example/', status=None, error=f.REFUSED), None, c.FAILURE),
        # the site answers, or may answer later: not a failure
        (_answer('http://a.example/', status=403), None, c.INCONCLUSIVE),
        (_answer('http://a.example/', status=429), None, c.INCONCLUSIVE),
        (_answer('http://a.example/', status=503), None, c.INCONCLUSIVE),
        (
            _answer('http://a.example/', status=None, error=f.TIMEOUT),
            None,
            c.INCONCLUSIVE,
        ),
        (
            _answer('http://a.example/', status=None, error=f.TLS_CHAIN),
            None,
            c.INCONCLUSIVE,
        ),
        (
            _answer('http://a.example/', status=None, error=f.DNS_TEMPORARY),
            None,
            c.INCONCLUSIVE,
        ),
        (_answer('http://a.example:8080/', status=None, error=f.PORT), None, c.BLOCKED),
    ],
)
def test_classify(answer, reference, outcome):
    assert c.classify(answer.url, answer, reference) == outcome


def _check(**kwargs):
    return LinkCheck(
        url='http://a.example/',
        host='a.example',
        status=UNCHECKED,
        failures=0,
        last_seen_at=NOW,
        **kwargs,
    )


def test_dead_after_failures_weeks_apart():
    check = _check()
    failure = _answer(check.url, status=404)
    for days in (0, 7):
        checker.apply(check, c.FAILURE, failure, NOW + timedelta(days=days))
        assert check.status == FAILING
    # a third failure, but not 14 days after the first one
    checker.apply(check, c.FAILURE, failure, NOW + timedelta(days=13))
    assert (check.status, check.failures) == (FAILING, 3)
    checker.apply(check, c.FAILURE, failure, NOW + timedelta(days=14))
    assert check.status == DEAD
    assert check.next_check_at >= NOW + timedelta(days=14 + 72)

    # a site down for a while: nothing changes
    checker.apply(check, c.INCONCLUSIVE, _answer(check.url, status=503), NOW)
    assert (check.status, check.failures) == (DEAD, 4)

    # back
    checker.apply(check, c.OK, _answer(check.url, title='Topo'), NOW)
    assert (check.status, check.failures, check.first_failure_at) == (OK, 0, None)
    assert (check.first_title, check.last_ok_at) == ('Topo', NOW)
    assert NOW + timedelta(days=24) <= check.next_check_at <= NOW + timedelta(days=36)


def test_genuine_until_the_page_changes():
    check = _check(first_title='Topo', review=GENUINE, reviewed_by=1, reviewed_at=NOW)
    checker.apply(check, c.OFFSITE, _answer(check.url, title='Topo'), NOW)
    assert check.review == GENUINE
    checker.apply(check, c.SUSPECT, _answer(check.url, title='Casino'), NOW)
    assert (check.status, check.review, check.reviewed_by) == (SUSPECT, None, None)


def _robots(network, text, host='example.com'):
    network[f'http://{host}/robots.txt'] = FakeResponse(
        200, {'Content-Type': 'text/plain'}, text.encode()
    )


def test_robots(network):
    host = LinkHost(host='example.com')
    _robots(network, 'User-agent: *\nDisallow: /private/\n')
    assert checker.robots_allow(host, 'http://example.com/topo', NOW) == (True, True)
    # read again after a week only
    assert checker.robots_allow(host, 'http://example.com/private/x', NOW) == (
        False,
        False,
    )
    # no robots.txt: everything allowed
    del network['http://example.com/robots.txt']
    later = NOW + timedelta(days=8)
    assert checker.robots_allow(host, 'http://example.com/private/x', later) == (
        True,
        True,
    )
    # unreachable: try later
    network['http://example.com/robots.txt'] = FakeResponse(503)
    host.robots_fetched_at = None
    assert checker.robots_allow(host, 'http://example.com/', NOW)[0] is None


def _write(session, document, text):
    locale = document.locales[0]
    locale.description = text
    session.flush()
    update_text_references([locale])
    session.flush()


def _statuses(session):
    session.expire_all()
    return {
        check.url: check.status
        for check in session.query(LinkCheck).order_by(LinkCheck.url)
    }


def test_run(network, session, docs, monkeypatch):  # noqa: F811
    monkeypatch.setattr(checker.time, 'sleep', lambda s: None)
    monkeypatch.setattr(checker, 'network_ok', lambda: True)
    _write(
        session,
        docs.route1,
        '[a](http://example.com/a) [b](http://example.com/b) '
        '[c](http://example.com/private/c) [o](http://other.example/o) '
        '[p](http://parked.example/) [r](http://redis/)',
    )
    # an outing: not collaborative
    _write(session, docs.outing1, '[x](http://example.com/outing)')
    _robots(network, 'User-agent: *\nDisallow: /private/\n')
    network['http://example.com/a'] = _page('Topo A')
    network['http://example.com/b'] = _page('Topo B')
    network['http://other.example/o'] = _redirect('http://parked.example/')
    network['http://parked.example/'] = _page('Domain', 'Buy this domain')
    # one URL per host per run (robots.txt first): 4 hosts
    assert checker.run_in(DBSession, 10, NOW) == 8
    statuses = _statuses(session)
    assert 'http://example.com/outing' not in statuses
    assert list(statuses.values()).count(UNCHECKED) == 2
    assert statuses['http://redis/'] == FAILING

    # a host waits a minute
    assert checker.run_in(DBSession, 10, NOW) == 0
    later = NOW + timedelta(minutes=2)
    assert checker.run_in(DBSession, 10, later) == 1
    # blocked by robots.txt (cached): no request
    assert checker.run_in(DBSession, 10, later + timedelta(minutes=2)) == 0
    assert _statuses(session) == {
        'http://example.com/a': OK,
        'http://example.com/b': OK,
        'http://example.com/private/c': BLOCKED,
        'http://other.example/o': c.PARKED,
        'http://parked.example/': c.PARKED,
        'http://redis/': FAILING,
    }

    # a URL no text links any more is forgotten after 90 days
    _write(session, docs.route1, '[a](http://example.com/a)')
    checker.sync_link_checks(session, NOW + timedelta(days=91))
    assert list(_statuses(session)) == ['http://example.com/a']


def test_one_run_at_a_time(db_engine, monkeypatch):
    def fail(*args):
        raise AssertionError('a second run must not start')

    monkeypatch.setattr(checker, '_run', fail)
    with db_engine.connect() as other:
        other.execute(text('select pg_advisory_lock(:key)'), {'key': checker._LOCK_KEY})
        try:
            assert checker.run(db_engine) == 0
        finally:
            other.execute(
                text('select pg_advisory_unlock(:key)'), {'key': checker._LOCK_KEY}
            )
            other.commit()


def test_nul_characters_dropped(network):
    network['http://example.com/'] = FakeResponse(
        200, {'Content-Type': 'text/html'}, b'<title>To\x00po</title>\x00'
    )
    answer = f.fetch('http://example.com/')
    assert (answer.title, '\x00' in answer.text) == ('Topo', False)


def test_an_error_does_not_stop_the_run(network, session, docs, monkeypatch):  # noqa: F811
    monkeypatch.setattr(checker.time, 'sleep', lambda s: None)
    monkeypatch.setattr(checker, 'network_ok', lambda: True)
    _write(
        session, docs.route1, '[a](http://example.com/a) [o](http://other.example/o)'
    )
    network['http://other.example/o'] = _page('Topo O')
    real_fetch = checker.fetch

    def fetch(url, read_body=True):
        if url == 'http://example.com/a':
            raise RuntimeError('odd page')
        return real_fetch(url, read_body)

    monkeypatch.setattr(checker, 'fetch', fetch)
    _robots(network, '')
    checker.run_in(DBSession, 10, NOW)

    session.expire_all()
    odd = session.get(LinkCheck, 'http://example.com/a')
    assert odd.status == UNCHECKED
    assert odd.next_check_at.astimezone(UTC) == NOW + checker.FAILING_INTERVAL
    assert session.get(LinkCheck, 'http://other.example/o').status == OK
