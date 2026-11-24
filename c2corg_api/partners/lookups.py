"""Small key/value caches adapters use to avoid repeated requests."""

import copy
from typing import Protocol


class LookupCache(Protocol):
    def get(self, key: str) -> dict | None: ...

    def put(self, key: str, data: dict) -> None: ...


class MemoryLookupCache:
    """A LookupCache in memory (tests, one-shot runs)."""

    def __init__(self):
        self._data: dict[str, dict] = {}

    def get(self, key: str) -> dict | None:
        data = self._data.get(key)
        return None if data is None else copy.deepcopy(data)

    def put(self, key: str, data: dict) -> None:
        self._data[key] = copy.deepcopy(data)
