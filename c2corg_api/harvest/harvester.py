"""What a harvester is: its sources, how to fetch one and store what it got."""

import hashlib
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from c2corg_api.harvest.policy import Policy


class NotModified(Exception):
    """The source answered 304: nothing new since the last fetch."""


@dataclass(frozen=True)
class State:
    """What the last fetch of a source left, for a conditional GET."""

    etag: str | None = None
    last_modified: str | None = None
    content_sha256: bytes | None = None
    data: dict = field(default_factory=dict)

    def conditional_headers(self):
        """Return the headers of a GET answered 304 if nothing changed."""
        headers = {}
        if self.etag:
            headers['If-None-Match'] = self.etag
        if self.last_modified:
            headers['If-Modified-Since'] = self.last_modified
        return headers


@dataclass(frozen=True)
class Payload:
    """A content fetched from a source (b'' when the source has nothing)."""

    content: bytes
    content_type: str | None = None
    etag: str | None = None
    last_modified: str | None = None

    @property
    def sha256(self):
        return hashlib.sha256(self.content).digest()

    @classmethod
    def of(cls, response):
        """Return the payload of an answer of requests, raise NotModified on 304."""
        if response.status_code == 304:
            raise NotModified()
        headers = response.headers
        return cls(
            # no content: no bulletin (404)
            response.content if response.ok else b'',
            headers.get('Content-Type'),
            headers.get('ETag'),
            headers.get('Last-Modified'),
        )


class Harvester:
    """The sources of a kind of data, fetched by the runner (harvest.runner).

    `fetch` and `store` run in a thread: any exception is an error of the
    source, retried later (policy).
    """

    name = None
    policy = Policy()

    def sources(self):
        """Return the keys of the sources (synced into harvest_sources)."""
        raise NotImplementedError

    def url(self, source):
        """Return the URL of a source (its host limits the concurrent fetches)."""
        raise NotImplementedError

    def host(self, source):
        return urlsplit(self.url(source)).hostname

    def fetch(self, source, state):
        """Return the Payload of a source, or raise NotModified."""
        raise NotImplementedError

    def store(self, session, source, payload):
        """Store a new content of a source: tell if it holds a new publication."""
        raise NotImplementedError

    def source_id(self, source):
        return f'{self.name}:{source}'
