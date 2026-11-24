"""Small key/value caches adapters use to avoid repeated requests."""

import json
from typing import Protocol


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
