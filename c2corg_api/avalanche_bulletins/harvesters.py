"""The harvesters of the avalanche bulletins (see c2corg_api.harvest)."""
# The requests and the parsing of the on-demand fetch (meteofrance, caaml),
# the bulletins stored by avalanche_bulletins.store. The PDF of Météo-France
# stays fetched on demand.

from datetime import time

from c2corg_api.avalanche_bulletins import caaml, meteofrance, store
from c2corg_api.harvest.harvester import Harvester, Payload
from c2corg_api.harvest.policy import Policy, Window
from c2corg_api.models.common.attributes import default_langs

# the services publish at about 16:00-17:00, some update at about 08:00
# (cache.PUBLICATIONS); nothing in summer
AVALANCHE_POLICY = Policy(
    season=((11, 1), (6, 30)),
    windows=(Window(time(7), time(10), 15), Window(time(15, 30), time(19), 15)),
    default_every=60,
)


class MeteoFranceHarvester(Harvester):
    """The BRA of each massif (source: its EAWS region id, FR-03)."""

    name = 'avalanche.meteofrance'
    policy = AVALANCHE_POLICY

    def sources(self):
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
        return store.save(
            session, 'meteofrance', 'fr', bulletins, self.source_id(source)
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
            return False
        bulletins = caaml.parse(payload.content, service_id, lang)
        return store.save(session, service_id, lang, bulletins, self.source_id(source))
