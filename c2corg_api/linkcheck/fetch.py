"""Fetch a page of another site for the link checker, safely.

The URLs are written by users: the server must not be made to request its
own network (the database, redis, cloud metadata...). Every request, and
every redirection, goes to a public address only: the host is resolved, all
its addresses must be public, and the connection is made to that address
(not resolved again, which could give another one). Only http and https on
their usual ports.
"""

import html
import ipaddress
import re
import socket
import time
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit, urlunsplit

import certifi
import urllib3
from urllib3.exceptions import (
    ConnectTimeoutError,
    NewConnectionError,
    ProtocolError,
    ReadTimeoutError,
    SSLError,
)

USER_AGENT = (
    'camptocamp-linkcheck/1.0 (+https://forum.camptocamp.org/c/'
    'site-et-association/site-c2c-suggestions-bugs-et-problemes/136)'
)

PORTS = {'http': 80, 'https': 443}
MAX_REDIRECTS = 5
MAX_BYTES = 256 * 1024
CONNECT_TIMEOUT = 10
# for the whole answer, redirections included
TOTAL_TIMEOUT = 20

# kinds of errors (LinkCheck.error)
DNS = 'dns'  # no such domain
DNS_TEMPORARY = 'dns_temporary'
PRIVATE = 'private'  # resolves to an address of a private network
PORT = 'port'  # not the usual port of http(s)
SCHEME = 'scheme'  # a redirection to another scheme than http(s)
REFUSED = 'refused'
TLS = 'tls'  # expired, self-signed, for another name...
# a certificate whose chain is incomplete: browsers complete it, not us
TLS_CHAIN = 'tls_chain'
TIMEOUT = 'timeout'
CONNECTION = 'connection'
TOO_MANY_REDIRECTS = 'too_many_redirects'

_TITLE_RE = re.compile(rb'<title[^>]*>(.*?)</title\s*>', re.IGNORECASE | re.DOTALL)
_META_CHARSET_RE = re.compile(rb'<meta[^>]+charset=["\']?([\w-]+)', re.IGNORECASE)
_CONTENT_CHARSET_RE = re.compile(r'charset=["\']?([\w-]+)', re.IGNORECASE)


@dataclass
class Answer:
    """What a URL gave: the last answer after the redirections, or an error."""

    url: str
    # the URLs requested, the first one included
    urls: list = field(default_factory=list)
    http_status: int | None = None
    error: str | None = None
    content_type: str = ''
    # the start of the body, decoded (pages only)
    text: str = ''
    title: str | None = None

    @property
    def final_url(self):
        return self.urls[-1] if self.urls else self.url


class FetchError(Exception):
    def __init__(self, kind):
        super().__init__(kind)
        self.kind = kind


def resolve_public(host, port):
    """Return a public address of a host, or raise FetchError."""
    # all its addresses must be public: a name that also resolves to a
    # private address is refused (the connection could go there)
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        if e.errno in (socket.EAI_NONAME, getattr(socket, 'EAI_NODATA', -5)):
            raise FetchError(DNS) from e
        raise FetchError(DNS_TEMPORARY) from e
    except UnicodeError as e:
        raise FetchError(DNS) from e
    addresses = []
    for family, _, _, _, sockaddr in infos:
        address = ipaddress.ip_address(sockaddr[0])
        if not address.is_global or address.is_multicast:
            raise FetchError(PRIVATE)
        addresses.append((family != socket.AF_INET, str(address)))
    if not addresses:
        raise FetchError(DNS)
    # IPv4 first
    return sorted(addresses)[0][1]


def _target(url):
    """Return (scheme, host, port, path) of an http(s) URL, or raise FetchError."""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in PORTS:
        raise FetchError(SCHEME)
    try:
        port = parts.port or PORTS[scheme]
    except ValueError as e:
        raise FetchError(PORT) from e
    if port != PORTS[scheme]:
        raise FetchError(PORT)
    host = (parts.hostname or '').rstrip('.')
    if not host:
        raise FetchError(DNS)
    path = urlunsplit(('', '', parts.path or '/', parts.query, ''))
    return scheme, host, port, path


def _open(scheme, host, port, path, deadline):
    """Send a GET to a public address of the host; return the response."""
    address = resolve_public(host, port)
    timeout = urllib3.Timeout(
        connect=CONNECT_TIMEOUT, read=max(1.0, deadline - time.monotonic())
    )
    if scheme == 'https':
        pool = urllib3.HTTPSConnectionPool(
            address,
            port,
            server_hostname=host,
            assert_hostname=host,
            cert_reqs='CERT_REQUIRED',
            ca_certs=certifi.where(),
            timeout=timeout,
            retries=False,
        )
    else:
        pool = urllib3.HTTPConnectionPool(address, port, timeout=timeout, retries=False)
    headers = {
        'Host': host,
        'User-Agent': USER_AGENT,
        'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
        'Accept-Language': 'fr,en;q=0.8,*;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
    }
    try:
        return pool.urlopen(
            'GET',
            path,
            headers=headers,
            redirect=False,
            retries=False,
            preload_content=False,
            decode_content=True,
        )
    except SSLError as e:
        message = str(e).lower()
        if 'unable to get local issuer' in message or 'first certificate' in message:
            raise FetchError(TLS_CHAIN) from e
        raise FetchError(TLS) from e
    except (ConnectTimeoutError, ReadTimeoutError) as e:
        raise FetchError(TIMEOUT) from e
    except NewConnectionError as e:
        if isinstance(e.__cause__, ConnectionRefusedError) or 'refused' in str(e):
            raise FetchError(REFUSED) from e
        raise FetchError(CONNECTION) from e
    except (ProtocolError, urllib3.exceptions.HTTPError, OSError) as e:
        raise FetchError(CONNECTION) from e


def _read(response, deadline):
    """Return the start of the body (MAX_BYTES at most), before the deadline."""
    chunks = []
    size = 0
    try:
        for chunk in response.stream(16 * 1024):
            chunks.append(chunk)
            size += len(chunk)
            if size >= MAX_BYTES or time.monotonic() > deadline:
                break
    except ReadTimeoutError, ProtocolError, urllib3.exceptions.HTTPError, OSError:
        # what was received is enough to see the page
        pass
    finally:
        response.release_conn()
    return b''.join(chunks)[:MAX_BYTES]


def _decode(body, content_type):
    match = _CONTENT_CHARSET_RE.search(content_type) or _META_CHARSET_RE.search(
        body[:4096]
    )
    charset = match.group(1) if match else 'utf-8'
    if isinstance(charset, bytes):
        charset = charset.decode('ascii', 'replace')
    try:
        return body.decode(charset, 'replace')
    except LookupError:
        return body.decode('utf-8', 'replace')


def page_title(text):
    """Return the title of an HTML page, cleaned (300 characters), or None."""
    match = _TITLE_RE.search(text.encode('utf-8', 'replace'))
    if not match:
        return None
    title = html.unescape(match.group(1).decode('utf-8', 'replace'))
    title = ' '.join(title.split())
    return title[:300] or None


def fetch(url, read_body=True):
    """Request a URL, following the redirections (each one checked); an Answer."""
    answer = Answer(url=url)
    deadline = time.monotonic() + TOTAL_TIMEOUT
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        answer.urls.append(current)
        try:
            scheme, host, port, path = _target(current)
            response = _open(scheme, host, port, path, deadline)
        except FetchError as e:
            answer.error = e.kind
            return answer
        answer.http_status = response.status
        location = response.headers.get('Location')
        if 300 <= response.status < 400 and location:
            response.drain_conn()
            response.release_conn()
            current = urljoin(current, location.strip())
            continue
        answer.content_type = response.headers.get('Content-Type', '')
        content_type = answer.content_type.lower()
        # pages and texts (robots.txt): not images, PDF...
        if read_body and (
            not content_type
            or content_type.startswith('text/')
            or 'html' in content_type
        ):
            answer.text = _decode(_read(response, deadline), answer.content_type)
            if 'html' in content_type or not content_type:
                answer.title = page_title(answer.text)
        else:
            response.release_conn()
        return answer
    answer.error = TOO_MANY_REDIRECTS
    return answer
