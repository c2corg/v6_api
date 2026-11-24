"""HTTP transports: the real one, one replaying fixtures, one recording."""

import datetime
import json
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlsplit

import requests

from c2corg_api.partners.adapter import SourceBlocked, SourceDown
from c2corg_api.partners.model import RateLimit

CHALLENGE_MARKERS = ('Just a moment...', 'cf-chl')
# how much of a body is searched for a challenge marker
CHALLENGE_SCAN_BYTES = 64 * 1024


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes
    url: str

    def header(self, name: str) -> str | None:
        """Return a header value, whatever the case of its name."""
        wanted = name.lower()
        for key, value in self.headers.items():
            if key.lower() == wanted:
                return value
        return None

    def json(self) -> Any:
        return json.loads(self.text())

    def text(self, encoding: str | None = None) -> str:
        """Decode the body: `encoding`, else the charset header, else UTF-8."""
        if encoding is None:
            match = re.search(
                r'charset=["\']?([\w.-]+)', self.header('content-type') or ''
            )
            encoding = match.group(1) if match else 'utf-8'
        try:
            return self.body.decode(encoding, errors='replace')
        except LookupError:
            return self.body.decode('utf-8', errors='replace')


class Transport(Protocol):
    def get(
        self,
        url: str,
        *,
        params: Mapping[str, str | int] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse: ...

    @property
    def request_count(self) -> int: ...


def is_challenge(response: HttpResponse) -> bool:
    """Whether the response is an anti-bot challenge page (Cloudflare...).

    The `cf-mitigated` header is trusted on any status. The body is only
    searched on an error status: a 200 page or JSON may quote the markers in
    user text (a title "Just a moment..."), and challenges come with 403/503.
    """
    if (response.header('cf-mitigated') or '').lower() == 'challenge':
        return True
    if response.status < 400:
        return False
    head = response.body[:CHALLENGE_SCAN_BYTES].decode('utf-8', errors='replace')
    return any(marker in head for marker in CHALLENGE_MARKERS)


def classify(response: HttpResponse) -> HttpResponse:
    """Return the response, or raise for a block or a failure.

    SourceBlocked on 401/403/429 or a challenge page, SourceDown on 5xx; any
    other status (404 included) is returned.
    """
    if is_challenge(response):
        raise SourceBlocked(
            f'challenge page from {response.url} (HTTP {response.status})'
        )
    if response.status in (401, 403, 429):
        raise SourceBlocked(f'HTTP {response.status} from {response.url}')
    if response.status >= 500:
        raise SourceDown(f'HTTP {response.status} from {response.url}')
    return response


class HttpTransport:
    """requests-based transport: user agent, timeouts, politeness, budget."""

    USER_AGENT = 'camptocamp.org partner-index (+https://www.camptocamp.org)'

    def __init__(
        self,
        rate: RateLimit,
        *,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.rate = rate
        self.session = session if session is not None else requests.Session()
        self._sleep = sleep
        self._clock = clock
        self._last_request: dict[str, float] = {}
        self._count = 0

    @property
    def request_count(self) -> int:
        return self._count

    def get(self, url, *, params=None, headers=None) -> HttpResponse:
        if self._count >= self.rate.max_requests_per_run:
            raise SourceDown('request budget exhausted')
        host = urlsplit(url).netloc.lower()
        last = self._last_request.get(host)
        if last is not None:
            wait = self.rate.min_interval_s - (self._clock() - last)
            if wait > 0:
                self._sleep(wait)
        self._count += 1
        self._last_request[host] = self._clock()
        request_headers = {'User-Agent': self.USER_AGENT, **(headers or {})}
        try:
            raw = self.session.get(
                url,
                params=params,
                headers=request_headers,
                timeout=(5, self.rate.timeout_s),
            )
        except requests.Timeout as e:
            raise SourceDown(f'timeout on {url}') from e
        except requests.ConnectionError as e:
            raise SourceDown(f'connection error on {url}') from e
        except requests.RequestException as e:
            # truncated body, too many redirects...: availability, not parsing
            raise SourceDown(f'{type(e).__name__} on {url}') from e
        # the interval counts from the end of the request
        self._last_request[host] = self._clock()
        return classify(
            HttpResponse(
                status=raw.status_code,
                headers=dict(raw.headers),
                body=raw.content,
                url=str(raw.url or url),
            )
        )


def _split_url(url: str, params: Mapping[str, Any] | None):
    """Return (scheme, host, path) and all the params, as strings."""
    parts = urlsplit(url)
    all_params = dict(parse_qsl(parts.query, keep_blank_values=True))
    all_params.update({k: str(v) for k, v in (params or {}).items()})
    return (parts.scheme, parts.netloc.lower(), parts.path), all_params


class FixtureTransport:
    """Replays the responses of `<fixtures_dir>/<source>/manifest.json`.

    Never touches the network. An entry matches a request with the same
    scheme, host and path, when all the entry params (as strings) are among the
    request params. The first matching entry wins. The entry status is
    honoured and goes through the same classification as a live response.
    """

    def __init__(self, fixtures_dir: Path, source: str):
        self.source = source
        self.directory = Path(fixtures_dir) / source
        self.manifest: dict[str, Any] = json.loads(
            (self.directory / 'manifest.json').read_text(encoding='utf-8')
        )
        self._count = 0

    @property
    def recorded_at(self) -> str | None:
        return self.manifest.get('recorded_at')

    @property
    def synthetic(self) -> bool:
        return bool(self.manifest.get('synthetic', False))

    @property
    def request_count(self) -> int:
        return self._count

    def get(self, url, *, params=None, headers=None) -> HttpResponse:
        self._count += 1
        target, request_params = _split_url(url, params)
        for entry in self.manifest.get('entries', []):
            entry_target, entry_params = _split_url(entry['url'], entry.get('params'))
            if entry_target != target:
                continue
            if any(
                request_params.get(key) != value for key, value in entry_params.items()
            ):
                continue
            return classify(self._response(entry, url))
        raise SourceDown(f'no fixture for {url} {dict(params or {})}')

    def _response(self, entry, url) -> HttpResponse:
        body = b''
        if entry.get('file'):
            body = (self.directory / entry['file']).read_bytes()
        response_headers = dict(entry.get('headers') or {})
        if entry.get('content_type'):
            response_headers.setdefault('Content-Type', entry['content_type'])
        return HttpResponse(
            status=int(entry.get('status', 200)),
            headers=response_headers,
            body=body,
            url=url,
        )


def _slug(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', text.lower()).strip('_')


class RecordingTransport:
    """Wraps a transport and records each response as a fixture file.

    Writes `<out_dir>/<source>/manifest.json` and the body files; the CLI
    `record` command uses it. `trim(url, body) -> bytes` can shrink a body
    before it is written (e.g. drop the media of the gulliver comments).
    """

    def __init__(
        self,
        inner: Transport,
        out_dir: Path,
        source: str,
        trim: Callable[[str, bytes], bytes] | None = None,
    ):
        self.inner = inner
        self.source = source
        self.directory = Path(out_dir) / source
        self.trim = trim
        self.entries: list[dict[str, Any]] = []
        self._names: set[str] = set()

    @property
    def request_count(self) -> int:
        return self.inner.request_count

    def get(self, url, *, params=None, headers=None) -> HttpResponse:
        response = self.inner.get(url, params=params, headers=headers)
        body = self.trim(url, response.body) if self.trim else response.body
        content_type = response.header('content-type') or ''
        name = self._file_name(url, params, content_type)
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / name).write_bytes(body)
        entry: dict[str, Any] = {
            'url': url,
            'status': response.status,
            'content_type': content_type,
            'file': name,
        }
        if params:
            entry['params'] = {k: str(v) for k, v in params.items()}
        self.entries.append(entry)
        self._write_manifest()
        return response

    def _file_name(self, url, params, content_type) -> str:
        path = urlsplit(url).path
        endpoint = _slug(path.rstrip('/').rsplit('/', 1)[-1]) or 'index'
        suffix = ''.join(
            f'_{_slug(str(k))}{_slug(str(v))}'
            for k, v in sorted((params or {}).items())
        )
        if 'json' in content_type:
            ext = 'json'
        elif 'html' in content_type:
            ext = 'html'
        else:
            ext = 'txt'
        base = f'{endpoint}{suffix}'
        name, n = f'{base}.{ext}', 1
        while name in self._names:
            n += 1
            name = f'{base}_{n}.{ext}'
        self._names.add(name)
        return name

    def _write_manifest(self):
        manifest = {
            'source': self.source,
            'recorded_at': datetime.datetime.now(datetime.UTC).date().isoformat(),
            'synthetic': False,
            'entries': self.entries,
        }
        (self.directory / 'manifest.json').write_text(
            json.dumps(manifest, indent=2) + '\n', encoding='utf-8'
        )
