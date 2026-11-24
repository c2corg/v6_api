"""The harvesters of the avalanche bulletins (see c2corg_api.harvest)."""
# The requests and the parsing of the on-demand fetch (meteofrance, caaml),
# the bulletins stored by avalanche_bulletins.store. The PDF of Météo-France
# stays fetched on demand.

import os
from datetime import time

from c2corg_api.avalanche_bulletins import caaml, meteofrance, store
from c2corg_api.harvest.harvester import Harvester, Payload, Stored
from c2corg_api.harvest.policy import Policy, Window
from c2corg_api.models.common.attributes import default_langs

# the services publish at about 16:00-17:00, some update at about 08:00
# (cache.PUBLICATIONS), then rarely change theirs; nothing in summer
AVALANCHE_POLICY = Policy(
    season=((11, 1), (6, 30)),
    windows=(Window(time(7), time(10), 15), Window(time(15, 30), time(19), 15)),
    default_every=60,
)


class MeteoFranceHarvester(Harvester):
    """The BRA of each massif (source: its EAWS region id, FR-03)."""

    name = 'avalanche.meteofrance'
    policy = AVALANCHE_POLICY
    # the quota of the key is 50 a minute, shared with the PDFs fetched on
    # demand by the API: the 35 massifs in a tick, and a margin
    requests_per_minute = 40

    def sources(self):
        # none without the key of the API: the sources are disabled
        if not os.getenv('METEOFRANCE_API_KEY'):
            return []
        return [f'FR-{massif:02d}' for massif in sorted(meteofrance.MASSIFS)]

    def url(self, source):
        return meteofrance.API_URL

    def fetch(self, source, state):
        massif = meteofrance.massif_of(source)
        return Payload.of(
            meteofrance.request(massif, 'xml', state.conditional_headers())
        )

    def store(self, session, source, payload):
        bulletins = meteofrance.parse(payload.content, meteofrance.massif_of(source))
        return Stored(
            store.save(session, 'meteofrance', 'fr', bulletins, self.source_id(source))
        )


class CaamlHarvester(Harvester):
    """The latest file of each EAWS service and language (source: CH:fr)."""

    # the languages of c2c that each service publishes
    name = 'avalanche.caaml'
    policy = AVALANCHE_POLICY

    def sources(self):
        return [
            f'{service_id}:{lang}'
            for service_id, service in caaml.SERVICES.items()
            for lang in default_langs
            if lang in service.langs
        ]

    def url(self, source):
        service_id, lang = source.split(':')
        return caaml.SERVICES[service_id].url_for(service_id, lang)

    def fetch(self, source, state):
        service_id, lang = source.split(':')
        return Payload.of(caaml.request(service_id, lang, state.conditional_headers()))

    def store(self, session, source, payload):
        service_id, lang = source.split(':')
        # no file out of season
        if not payload.content:
            return Stored()
        bulletins = caaml.parse(payload.content, service_id, lang)
        return Stored(
            store.save(session, service_id, lang, bulletins, self.source_id(source))
        )
