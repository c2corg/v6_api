import json

import pytest
import requests

from c2corg_api.partners.adapter import SourceBlocked, SourceDown
from c2corg_api.partners.model import RateLimit
from c2corg_api.partners.transport import (
    FixtureTransport,
    HttpResponse,
    HttpTransport,
    RecordingTransport,
)

CLOUDFLARE_BODY = b'<html><title>Just a moment...</title></html>'


class FakeRaw:
    def __init__(self, status=200, body=b'{}', headers=None, url=None):
        self.status_code = status
        self.content = body
        self.headers = headers or {}
        self.url = url


class FakeSession:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        item = self.responses.pop(0) if self.responses else FakeRaw()
        if isinstance(item, Exception):
            raise item
        return item


class FakeClock:
    def __init__(self):
        self.now = 100.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


RATE = RateLimit(min_interval_s=2.0, max_requests_per_run=3, timeout_s=20)
URL = 'https://example.org/api/list'


def make(*responses, rate=RATE):
    session = FakeSession(*responses)
    clock = FakeClock()
    transport = HttpTransport(rate, session=session, sleep=clock.sleep, clock=clock)
    return transport, session, clock


def test_http_response_json_and_text():
    response = HttpResponse(
        200, {'Content-Type': 'text/html; charset=latin-1'}, 'é'.encode('latin-1'), URL
    )
    assert response.text() == 'é'
    assert response.text('utf-8') == '�'
    assert HttpResponse(200, {}, '{"a": "é"}'.encode(), URL).json() == {'a': 'é'}
    unknown = HttpResponse(200, {'content-type': 'text/x; charset=nope'}, b'ok', URL)
    assert unknown.text() == 'ok'
    assert HttpResponse(200, {}, b'', URL).header('x') is None


def test_sends_user_agent_timeout_and_params():
    transport, session, _ = make(FakeRaw(body=b'{"a": 1}', url=URL + '?p=1'))
    response = transport.get(URL, params={'p': 1}, headers={'X-Key': 'k'})
    assert response.json() == {'a': 1}
    assert response.status == 200
    url, kwargs = session.calls[0]
    assert url == URL
    assert kwargs['params'] == {'p': 1}
    assert kwargs['timeout'] == (5, 20)
    assert kwargs['headers']['User-Agent'] == (
        'camptocamp.org partner-index (+https://www.camptocamp.org)'
    )
    assert kwargs['headers']['X-Key'] == 'k'
    assert transport.request_count == 1


def test_default_session_is_created():
    assert isinstance(HttpTransport(RATE).session, requests.Session)


def test_min_interval_is_respected():
    transport, _, clock = make()
    transport.get(URL)
    assert clock.sleeps == []
    clock.now += 0.5  # only 0.5 s since the first request
    transport.get(URL)
    assert clock.sleeps == [pytest.approx(1.5)]
    clock.now += 10  # long enough: no sleep
    transport.get(URL)
    assert clock.sleeps == [pytest.approx(1.5)]


def test_interval_is_tracked_per_host():
    transport, _, clock = make()
    transport.get('https://a.example/x')
    transport.get('https://b.example/x')
    assert clock.sleeps == []
    clock.now += 0.5
    transport.get('https://a.example/y')
    assert clock.sleeps == [pytest.approx(1.5)]


def test_budget_exhaustion():
    transport, session, _ = make()
    for _ in range(3):
        transport.get(URL)
    with pytest.raises(SourceDown, match='request budget exhausted'):
        transport.get(URL)
    assert len(session.calls) == 3
    assert transport.request_count == 3


@pytest.mark.parametrize('status', [401, 403, 429])
def test_blocked_statuses(status):
    transport, _, _ = make(FakeRaw(status=status, url=URL))
    with pytest.raises(SourceBlocked) as error:
        transport.get(URL)
    assert str(status) in str(error.value)
    assert 'challenge' not in str(error.value)


def test_cloudflare_403_body_is_a_challenge():
    transport, _, _ = make(FakeRaw(status=403, body=CLOUDFLARE_BODY))
    with pytest.raises(SourceBlocked, match='challenge'):
        transport.get(URL)


@pytest.mark.parametrize(
    ('status', 'headers', 'body'),
    [
        (200, {'cf-mitigated': 'challenge'}, b'<html/>'),
        (403, {'CF-Mitigated': 'challenge'}, b''),
        (200, {}, b'<script src="/cdn-cgi/challenge-platform/cf-chl-bypass">'),
        (503, {}, CLOUDFLARE_BODY),
    ],
)
def test_challenge_detection(status, headers, body):
    transport, _, _ = make(FakeRaw(status=status, body=body, headers=headers))
    with pytest.raises(SourceBlocked, match='challenge'):
        transport.get(URL)


def test_ordinary_pages_are_not_challenges():
    transport, _, _ = make(
        FakeRaw(body=b'<html>a normal page</html>', headers={'cf-mitigated': 'other'})
    )
    assert transport.get(URL).status == 200


@pytest.mark.parametrize('status', [500, 502, 503, 504])
def test_5xx_is_down(status):
    transport, _, _ = make(FakeRaw(status=status))
    with pytest.raises(SourceDown, match=str(status)):
        transport.get(URL)


def test_timeout_is_down():
    transport, _, _ = make(requests.Timeout('slow'))
    with pytest.raises(SourceDown, match='timeout'):
        transport.get(URL)
    assert transport.request_count == 1


def test_connection_error_is_down():
    transport, _, _ = make(requests.ConnectionError('refused'))
    with pytest.raises(SourceDown, match='connection'):
        transport.get(URL)


@pytest.mark.parametrize('status', [200, 204, 301, 400, 404])
def test_other_statuses_are_returned(status):
    transport, _, _ = make(FakeRaw(status=status, body=b'nope'))
    assert transport.get(URL).status == status


# fixtures


def write_fixtures(tmp_path, entries, files=None, **manifest):
    directory = tmp_path / 'demo'
    directory.mkdir()
    manifest = {'source': 'demo', 'entries': entries, **manifest}
    (directory / 'manifest.json').write_text(json.dumps(manifest))
    for name, content in (files or {}).items():
        (directory / name).write_bytes(content)
    return tmp_path


LIST_URL = 'https://www.example.org/api/list'


def test_fixture_transport_serves_files(tmp_path):
    root = write_fixtures(
        tmp_path,
        [
            {
                'url': LIST_URL,
                'params': {'page': '1'},
                'content_type': 'application/json',
                'file': 'p1.json',
            }
        ],
        {'p1.json': b'{"items": [1]}'},
        recorded_at='2026-11-24',
        synthetic=True,
    )
    transport = FixtureTransport(root, 'demo')
    response = transport.get(LIST_URL, params={'page': 1})
    assert response.status == 200
    assert response.json() == {'items': [1]}
    assert response.headers['Content-Type'] == 'application/json'
    assert transport.request_count == 1
    assert transport.synthetic is True
    assert transport.recorded_at == '2026-11-24'
    assert transport.manifest['source'] == 'demo'


def test_fixture_manifest_flags_default(tmp_path):
    transport = FixtureTransport(write_fixtures(tmp_path, []), 'demo')
    assert transport.synthetic is False
    assert transport.recorded_at is None


def test_fixture_subset_matching_and_first_wins(tmp_path):
    root = write_fixtures(
        tmp_path,
        [
            {'url': LIST_URL, 'params': {'page': '2'}, 'file': 'two.txt'},
            {'url': LIST_URL, 'params': {'page': '1'}, 'file': 'one.txt'},
            {'url': LIST_URL, 'file': 'any.txt'},
        ],
        {'one.txt': b'one', 'two.txt': b'two', 'any.txt': b'any'},
    )
    transport = FixtureTransport(root, 'demo')
    # the request may have more params than the entry
    assert transport.get(LIST_URL, params={'page': 1, 'x': 'y'}).body == b'one'
    assert transport.get(LIST_URL, params={'page': '2'}).body == b'two'
    # an entry without params matches anything on that path
    assert transport.get(LIST_URL, params={'page': 3}).body == b'any'
    assert transport.get(LIST_URL).body == b'any'
    # params in the URL itself count
    assert transport.get(LIST_URL + '?page=1').body == b'one'


def test_fixture_matches_scheme_host_and_path(tmp_path):
    root = write_fixtures(
        tmp_path, [{'url': LIST_URL, 'file': 'a.txt'}], {'a.txt': b'a'}
    )
    transport = FixtureTransport(root, 'demo')
    for url in (
        'http://www.example.org/api/list',
        'https://other.example.org/api/list',
        'https://www.example.org/api/other',
    ):
        with pytest.raises(SourceDown, match='no fixture for'):
            transport.get(url)
    assert transport.get('https://WWW.example.org/api/list').body == b'a'


def test_fixture_params_must_be_present_and_equal(tmp_path):
    root = write_fixtures(
        tmp_path,
        [{'url': LIST_URL, 'params': {'page': '1'}, 'file': 'a.txt'}],
        {'a.txt': b'a'},
    )
    transport = FixtureTransport(root, 'demo')
    with pytest.raises(SourceDown, match='no fixture for'):
        transport.get(LIST_URL)
    with pytest.raises(SourceDown, match=r"no fixture for .*'page': 2"):
        transport.get(LIST_URL, params={'page': 2})


def test_fixture_status_goes_through_classification(tmp_path):
    root = write_fixtures(
        tmp_path,
        [
            {'url': 'https://s.example/403', 'status': 403, 'file': 'cf.html'},
            {'url': 'https://s.example/403plain', 'status': 403},
            {'url': 'https://s.example/503', 'status': 503},
            {'url': 'https://s.example/429', 'status': 429},
            {'url': 'https://s.example/404', 'status': 404, 'file': 'nf.txt'},
            {
                'url': 'https://s.example/hdr',
                'status': 200,
                'headers': {'cf-mitigated': 'challenge'},
            },
        ],
        {'cf.html': CLOUDFLARE_BODY, 'nf.txt': b'not found'},
    )
    transport = FixtureTransport(root, 'demo')
    with pytest.raises(SourceBlocked, match='challenge'):
        transport.get('https://s.example/403')
    with pytest.raises(SourceBlocked, match='403'):
        transport.get('https://s.example/403plain')
    with pytest.raises(SourceBlocked, match='429'):
        transport.get('https://s.example/429')
    with pytest.raises(SourceBlocked, match='challenge'):
        transport.get('https://s.example/hdr')
    with pytest.raises(SourceDown, match='503'):
        transport.get('https://s.example/503')
    response = transport.get('https://s.example/404')
    assert (response.status, response.body) == (404, b'not found')
    assert transport.request_count == 6


def test_fixture_no_match_counts_and_raises(tmp_path):
    transport = FixtureTransport(write_fixtures(tmp_path, []), 'demo')
    with pytest.raises(SourceDown, match='no fixture for'):
        transport.get(LIST_URL)
    assert transport.request_count == 1


def test_fixture_missing_manifest(tmp_path):
    with pytest.raises(FileNotFoundError):
        FixtureTransport(tmp_path, 'nothing')


# recording


def test_recording_transport_writes_files_and_manifest(tmp_path):
    (tmp_path / 'src').mkdir()
    inner_root = write_fixtures(
        tmp_path / 'src',
        [
            {
                'url': 'https://www.example.org/wp-json/commentglobal',
                'params': {'page': '1'},
                'content_type': 'application/json; charset=utf-8',
                'file': 'x.json',
            },
            {
                'url': 'https://www.example.org/Verhaeltnisse/',
                'content_type': 'text/html',
                'file': 'x.html',
            },
            {
                'url': 'https://www.example.org/Verhaeltnisse/',
                'content_type': 'text/html',
                'file': 'x.html',
            },
            {'url': 'https://www.example.org/', 'file': 'x.html'},
        ],
        {'x.json': b'{"media": 1, "a": 2}', 'x.html': b'<html>hi</html>'},
    )
    out = tmp_path / 'out'

    def trim(url, body):
        return (
            json.dumps({'a': json.loads(body)['a']}).encode()
            if url.endswith('commentglobal')
            else body
        )

    recorder = RecordingTransport(
        FixtureTransport(inner_root, 'demo'), out, 'demo', trim=trim
    )
    first = recorder.get(
        'https://www.example.org/wp-json/commentglobal', params={'page': 1}
    )
    assert first.json() == {'media': 1, 'a': 2}  # the caller gets the full response
    recorder.get('https://www.example.org/Verhaeltnisse/')
    recorder.get('https://www.example.org/Verhaeltnisse/')
    recorder.get('https://www.example.org/')
    assert recorder.request_count == 4

    files = sorted(p.name for p in (out / 'demo').iterdir())
    assert files == [
        'commentglobal_page1.json',
        'index.txt',
        'manifest.json',
        'verhaeltnisse.html',
        'verhaeltnisse_2.html',
    ]
    assert json.loads((out / 'demo' / 'commentglobal_page1.json').read_bytes()) == {
        'a': 2
    }

    # what was recorded can be replayed
    replay = FixtureTransport(out, 'demo')
    assert replay.synthetic is False
    assert replay.recorded_at
    assert replay.get(
        'https://www.example.org/wp-json/commentglobal', params={'page': 1}
    ).json() == {'a': 2}
    assert (
        replay.get('https://www.example.org/Verhaeltnisse/').body == b'<html>hi</html>'
    )
