"""The adapter contract: what a partner source implements."""

from typing import ClassVar, Protocol

from c2corg_api.partners.model import FetchContext, FetchResult, RateLimit


class SourceDisabled(Exception):
    """The source cannot run (missing secret): status 'disabled'."""


class SourceBlocked(Exception):
    """The source refuses us (401/403/429, challenge page): status 'blocked'.

    Raised by `HttpTransport`.
    """


class SourceDown(Exception):
    """The source does not answer (5xx, timeout, budget): status 'down'.

    Raised by `HttpTransport`.
    """


class ParseError(Exception):
    """The source answered something unexpected.

    Status 'failing' when it escapes `Adapter.fetch`.
    """


class Adapter(Protocol):
    name: ClassVar[str]  # 'skitour'
    site_name: ClassVar[str]  # 'skitour.fr' (credit line)
    site_url: ClassVar[str]  # 'https://skitour.fr'
    required_secrets: ClassVar[tuple[str, ...]]
    rate: ClassVar[RateLimit]

    def fetch(self, ctx: FetchContext) -> FetchResult: ...


def require_secrets(ctx: FetchContext, names: tuple[str, ...] | list[str]):
    """Raise SourceDisabled('<NAME> not set') for the first missing secret."""
    for name in names:
        if not ctx.secrets.get(name):
            raise SourceDisabled(f'{name} not set')
