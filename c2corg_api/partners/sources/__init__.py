"""The partner adapters.

Each adapter module registers its class in `REGISTRY` (see the skitour and
gulliver adapters). `SOURCE_NAMES` lists the known partner sources, whether
their adapter exists yet or not.
"""

from c2corg_api.partners.adapter import Adapter

SOURCE_NAMES = ('skitour', 'gulliver')

REGISTRY: dict[str, type[Adapter]] = {}

from c2corg_api.partners.sources.gulliver import GulliverAdapter  # noqa: E402

REGISTRY['gulliver'] = GulliverAdapter
