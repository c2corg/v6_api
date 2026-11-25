"""The partner adapters.

Each adapter module registers its class in `REGISTRY` (see the skitour and
gulliver adapters). `REGISTRY` is the one list of the partner sources (name,
credit `site_name` and `site_url` included): `SOURCE_NAMES` is derived from it.
"""

from c2corg_api.partners.adapter import Adapter
from c2corg_api.partners.sources.bivouak import BivouakAdapter
from c2corg_api.partners.sources.gulliver import GulliverAdapter
from c2corg_api.partners.sources.skitour import SkitourAdapter

REGISTRY: dict[str, type[Adapter]] = {
    'skitour': SkitourAdapter,
    'gulliver': GulliverAdapter,
    'bivouak': BivouakAdapter,
}

SOURCE_NAMES = tuple(REGISTRY)
