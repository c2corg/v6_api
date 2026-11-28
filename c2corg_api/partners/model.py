"""The data model shared by the adapters, the transports and the job."""

import datetime
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from c2corg_api.partners.lookups import LookupCache
    from c2corg_api.partners.transport import Transport

# `summit_match` and `area_centroid` are set by the job (location hints), never
# by an adapter
GeomQuality = Literal[
    'summit', 'start', 'route', 'summit_match', 'area_centroid', 'none'
]
SourceStatus = Literal[
    'never_run', 'ok', 'degraded', 'blocked', 'down', 'failing', 'disabled'
]


# the kinds of `HarvestedOuting.texts`
TEXT_KINDS = (
    'narrative',  # the report itself
    'conditions',  # observations on the conditions (dangers, notes)
    'access',  # the road, the parking, the approach
    'snow',  # the snow as the author describes it (quality, top / bottom)
    'equipment',  # the gear used
)
TEXT_MAX_LENGTH = 20000  # characters, per text


@dataclass(frozen=True, slots=True)
class RateLimit:
    """How politely a source is queried."""

    min_interval_s: float
    max_requests_per_run: int
    timeout_s: float


@dataclass(frozen=True, slots=True)
class HarvestedRoute:
    """The route (itinerary, "topo") an outing followed, as its partner names it.

    Only for the sites that give a route its own identity: a skitour.fr topo,
    a gulliver.it itinerary, a bivouak.net topo, a gipfelbuch.ch route.
    `external_id` is unique within the source: the id of the site, or (when the
    site gives the route no id where we read it) a key made of its names
    (`name:...`, see the adapter). The route is upserted by `(source,
    external_id)`: the outings of the same route share one row.
    """

    external_id: str  # <= 128 chars
    title: str  # plain text, <= 300 chars
    url: str | None = None  # the route page on the partner site
    summit_name: str | None = None
    elevation_max: int | None = None
    lon: float | None = None  # WGS 84
    lat: float | None = None
    # what lon / lat are: 'summit', 'start' or 'none' (as GeomQuality)
    geom_quality: GeomQuality = 'none'


@dataclass(frozen=True, slots=True)
class HarvestedOuting:
    """An outing as published by a partner site, normalised."""

    source: str
    external_id: str
    url: str
    title: str  # plain text, <= 300 chars, HTML stripped
    date: datetime.date
    activities: tuple[str, ...]  # c2c activity values, non-empty
    author: str | None = None
    author_url: str | None = None
    lang: str | None = None
    region: str | None = None
    source_activity: str | None = None
    ski_rating_min: str | None = None  # values of attributes.ski_ratings
    ski_rating_max: str | None = None
    rating_raw: str | None = None
    rating_system: str | None = None
    steep: bool = False
    elevation_max: int | None = None
    height_diff_up: int | None = None
    # values of attributes.orientation_types
    orientations: tuple[str, ...] = ()
    snow: Mapping[str, int | str] | None = None
    # the public GPX file of the report (https, on the partner site): a link
    # only, never fetched. Validated by the adapter.
    gpx_url: str | None = None
    # The free texts of the report, plain text (HTML stripped), keyed by kind:
    # see TEXT_KINDS. Stored by the job, never served by the API, never real in
    # a fixture (the recorder redacts them: REDACT_PATHS / REDACT_SELECTORS).
    texts: Mapping[str, str] | None = None
    lon: float | None = None  # WGS 84; the job transforms to 3857 in SQL
    lat: float | None = None
    geom_quality: GeomQuality = 'none'
    # Location hints for outings without coordinates (lat/lon None). The job,
    # not the adapter, resolves them against c2c data: `summit_name` (+
    # `elevation_max`) against the summit waypoints, `country` (ISO 3166-1
    # alpha-2) and `region` against the areas. Adapters fill what they know.
    summit_name: str | None = None
    country: str | None = None
    # the route(s) the outing followed, the main one first (a skitour.fr outing
    # can link several topos). Empty when the site has no route concept
    # (skitourenportal.eu, on-ice.it) or the outing names none.
    routes: tuple[HarvestedRoute, ...] = ()


@dataclass(frozen=True, slots=True)
class FetchContext:
    """What the job hands to `Adapter.fetch`."""

    since: datetime.date  # oldest outing date wanted
    now: datetime.datetime  # tz-aware, injected (tests freeze it)
    cursor: Mapping[str, Any] | None  # what the adapter returned last time
    transport: Transport
    lookups: LookupCache
    # e.g. {'SKITOUR_API_KEY': '...'}; a missing key means SourceDisabled
    secrets: Mapping[str, str]

    def __post_init__(self):
        if self.now.tzinfo is None or self.now.utcoffset() is None:
            raise ValueError('FetchContext.now must be time zone aware')


@dataclass(slots=True)
class FetchResult:
    """What `Adapter.fetch` returns."""

    outings: list[HarvestedOuting]
    # stored as is (JSON) and handed back next run; None clears it
    cursor: dict[str, Any] | None = None
    # items left out on purpose: 'unmapped_activity:<code>', 'too_old', ...
    skipped: Counter[str] = field(default_factory=Counter)
    # items that failed to parse (logged with their external id); counted
    # here only, not in `skipped`: the job's error budget reads this
    item_errors: int = 0
