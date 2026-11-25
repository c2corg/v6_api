"""Small key/value caches adapters use to avoid repeated requests."""

import json
import logging
from typing import Protocol

from c2corg_api.partners.adapter import SourceDown

log = logging.getLogger(__name__)


class LookupCache(Protocol):
    """Per source; `key` <= 128 chars ('route:57949'), `data` JSON (jsonb)."""

    def get(self, key: str) -> dict | None: ...

    def put(self, key: str, data: dict) -> None: ...


class MemoryLookupCache:
    """A LookupCache in memory (tests, one-shot runs).

    Stores JSON like the database cache does, so an adapter that puts a
    date or a tuple fails (or reads a list back) in its tests too.
    """

    def __init__(self):
        self._data: dict[str, str] = {}

    def get(self, key: str) -> dict | None:
        data = self._data.get(key)
        return None if data is None else json.loads(data)

    def put(self, key: str, data: dict) -> None:
        self._data[key] = json.dumps(data, allow_nan=False)


class LookupRequests:
    """The secondary requests of a run: detail pages, routes, summits.

    A listing that fails stops the run (`SourceDown`: status `down`), but the
    lookup of one item must not: `get` returns None when the site fails for that
    request (5xx, timeout, no fixture, spent budget), counts
    `skipped['lookup_failed']`, and the adapter keeps the hints of the item
    (region, summit name...) for the job to resolve. The next run asks again,
    as nothing is cached. `SourceBlocked` still propagates: a block means stop.

    After `max_consecutive_failures` failures in a row the site is taken for
    down: `available` turns false and the adapter defers the remaining lookups
    to the next run instead of waiting for more timeouts.
    """

    def __init__(self, ctx, result, max_consecutive_failures=3):
        self.ctx = ctx
        self.result = result
        self.max_consecutive_failures = max_consecutive_failures
        self.consecutive_failures = 0
        self.failures = 0

    @property
    def available(self) -> bool:
        return self.consecutive_failures < self.max_consecutive_failures

    def get(self, url, *, params=None):
        """Return the response of a lookup, or None when it failed."""
        try:
            response = self.ctx.transport.get(url, params=params)
        except SourceDown as e:  # SourceBlocked is not caught: stop the run
            self.failures += 1
            self.consecutive_failures += 1
            self.result.skipped['lookup_failed'] += 1
            log.info('lookup %s failed: %s', url, e)
            return None
        self.consecutive_failures = 0
        return response
