"""The partner adapters.

Each adapter module registers its class in `REGISTRY` (see the skitour and
gulliver adapters). `SOURCE_NAMES` lists the known partner sources, whether
their adapter exists yet or not.
"""

from c2corg_api.partners.adapter import Adapter
from c2corg_api.partners.sources.gulliver import GulliverAdapter
from c2corg_api.partners.sources.skitour import SkitourAdapter

SOURCE_NAMES = ('skitour', 'gulliver')

REGISTRY: dict[str, type[Adapter]] = {
    'skitour': SkitourAdapter,
    'gulliver': GulliverAdapter,
}
