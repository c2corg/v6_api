"""The avalanche bulletins published as CAAML v6 by the EAWS services."""
# Their latest file, read as is (c2corg/v6_api#2683): no converter. The URLs,
# names and languages come from the EAWS metadata (eaws-regions,
# outline_properties). A file holds the bulletins of all the regions of its
# service (Euregio's, of the three regions of Euregio).

from dataclasses import dataclass

import requests

from c2corg_api.avalanche_bulletins.cache import (
    TIMEOUT,
    USER_AGENT,
    UpstreamError,
    cached,
    main_date,
)

ALBINA = 'https://static.avalanche.report/bulletins/latest/{region}_{lang}_CAAMLv6.json'
LAWINEN_WARNUNG = (
    'https://static.lawinen-warnung.eu/bulletins/latest/{region}_{lang}_CAAMLv6.json'
)
AINEVA = 'https://bollettini.aineva.it/albina_files/latest/{region}_{lang}_CAAMLv6.json'
ALBINA_LANGS = ('en', 'de', 'it', 'fr', 'es', 'ca', 'oc')
AINEVA_LANGS = ('en', 'de', 'it', 'fr')


@dataclass(frozen=True)
class Service:
    url: str
    name: str
    website: str
    langs: tuple

    def url_for(self, region, lang):
        return self.url.format(region=region, lang=lang)

    def lang_for(self, lang):
        """Return the language to read: the one asked, else English."""
        if lang in self.langs:
            return lang
        return 'en' if 'en' in self.langs else self.langs[0]


# by EAWS region id: the regions of each service start with it (CH-4231)
SERVICES = {
    'CH': Service(
        'https://aws.slf.ch/api/bulletin/caaml/{lang}/json',
        'SLF',
        'https://www.slf.ch',
        ('en', 'de', 'it', 'fr'),
    ),
    'AT-02': Service(
        ALBINA, 'LWD Kärnten', 'https://lawinenwarndienst.ktn.gv.at', ALBINA_LANGS
    ),
    'AT-03': Service(
        LAWINEN_WARNUNG,
        'LWD Niederösterreich',
        'https://www.lawinenwarndienst-niederoesterreich.at',
        ('en', 'de'),
    ),
    'AT-04': Service(
        LAWINEN_WARNUNG,
        'LWD Oberösterreich',
        'https://oberoesterreich.avalanche-warnings.eu',
        ('en', 'de'),
    ),
    'AT-05': Service(
        LAWINEN_WARNUNG, 'LWD Salzburg', 'https://lawine.salzburg.at', ('en', 'de')
    ),
    'AT-06': Service(
        LAWINEN_WARNUNG,
        'LWD Steiermark',
        'https://www.lawine-steiermark.at',
        ('en', 'de', 'it'),
    ),
    'AT-07': Service(ALBINA, 'LWD Tirol', 'https://avalanche.report', ALBINA_LANGS),
    'AT-08': Service(
        LAWINEN_WARNUNG, 'LWD Vorarlberg', 'https://warnung.vorarlberg.at', ('en', 'de')
    ),
    'DE-BY': Service(
        LAWINEN_WARNUNG,
        'LWD Bayern',
        'https://lawinenwarndienst.bayern.de',
        ('en', 'de'),
    ),
    'ES-CT-L': Service(
        'https://static.lauegi.report/albina_files/latest/{region}_{lang}_CAAMLv6.json',
        "Centre de Lauegi d'Aran",
        'https://lauegi.report',
        ALBINA_LANGS,
    ),
    'IT-21': Service(
        AINEVA, 'AINEVA Piemonte', 'https://bollettini.aineva.it', AINEVA_LANGS
    ),
    'IT-23': Service(
        AINEVA, "AINEVA Valle d'Aosta", 'https://bollettini.aineva.it', AINEVA_LANGS
    ),
    'IT-25': Service(
        AINEVA, 'AINEVA Lombardia', 'https://bollettini.aineva.it', AINEVA_LANGS
    ),
    'IT-32-BZ': Service(
        ALBINA, 'Lawinenwarndienst Südtirol', 'https://avalanche.report', ALBINA_LANGS
    ),
    'IT-32-TN': Service(
        ALBINA, 'Meteotrentino', 'https://avalanche.report', ALBINA_LANGS
    ),
    'IT-34': Service(
        AINEVA, 'AINEVA Veneto', 'https://bollettini.aineva.it', AINEVA_LANGS
    ),
    'IT-36': Service(
        AINEVA,
        'AINEVA Friuli Venezia Giulia',
        'https://bollettini.aineva.it',
        AINEVA_LANGS,
    ),
    'IT-57': Service(
        AINEVA, 'AINEVA Marche', 'https://bollettini.aineva.it', AINEVA_LANGS
    ),
    'SI': Service(
        LAWINEN_WARNUNG,
        'ARSO',
        'https://meteo.arso.gov.si/met/en/weather/bulletin/mountain/avalanche/bulletin/',
        ('en', 'de', 'it'),
    ),
}


def service_of(region_id):
    """Return the id of the service of a region (CH-4231: CH), None if unknown."""
    matches = [
        id for id in SERVICES if region_id == id or region_id.startswith(f'{id}-')
    ]
    return max(matches, key=len) if matches else None


def bulletins(service_id, lang):
    """Return the latest bulletins of a service, in a language it publishes."""
    service = SERVICES[service_id]
    lang = service.lang_for(lang)

    def fetch():
        url = service.url_for(service_id, lang)
        try:
            response = requests.get(
                url, headers={'User-Agent': USER_AGENT}, timeout=TIMEOUT
            )
        except requests.exceptions.RequestException as e:
            raise UpstreamError(str(e)) from e
        # no file out of season
        if response.status_code == 404:
            return []
        if not response.ok:
            raise UpstreamError(f'{url} answered {response.status_code}')
        try:
            data = response.json()
        except ValueError as e:
            raise UpstreamError(f'{url} is not JSON') from e
        return [_normalized(b, service) for b in _checked(data, url)]

    return cached(f'caaml:{service_id}:{lang}', fetch)


def _checked(data, url):
    # the fields c2c relies on: a list of bulletins, their regions and validity
    try:
        found = data['bulletins']
        for b in found:
            if not all(isinstance(r['regionID'], str) for r in b['regions']):
                raise TypeError('a regionID is not a string')
            main_date(b['validTime'])
    except (KeyError, TypeError, ValueError) as e:
        raise UpstreamError(f'{url} is not CAAML v6: {e!r}') from e
    return found


def _normalized(bulletin, service):
    # the provider (for the attribution) and the day of the bulletin are not
    # always given
    bulletin.setdefault('source', {}).setdefault(
        'provider', {'name': service.name, 'website': service.website}
    )
    albina = bulletin.setdefault('customData', {}).setdefault('ALBINA', {})
    albina.setdefault('mainDate', main_date(bulletin['validTime']))
    return bulletin
