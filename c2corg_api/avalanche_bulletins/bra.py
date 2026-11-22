"""The avalanche bulletin of Météo-France (BRA) as a CAAML v6 bulletin."""
# The XML of the DPBRA API, root BULLETINS_NEIGE_AVALANCHE. What CAAML has no
# field for goes to customData.MeteoFrance: avalancheProneLocation is the key
# pyAvaCore uses too, so this bulletin reads as the one of avalanches.org.

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import ParseError, fromstring

PARIS = ZoneInfo('Europe/Paris')

GLUED_SENTENCES = re.compile(r'([.!?])(?=[A-ZÀ-ÖØ-Þ])')
LIST_ITEMS = re.compile(r'\s*\*\s*')
# the headings of the sections of the texts, each on its own line
SECTIONS = re.compile(
    r'\s*\b(?=(?:Déclenchements provoqués|Départs spontanés|Observables'
    r'|Enneigement|Limite skiable|Qualité de la neige)\b[^:.]{0,40}:)'
)

PROVIDER = {
    'name': 'Météo-France',
    'website': 'https://meteofrance.com/meteo-montagne',
}

DANGER_RATINGS = {
    1: 'low',
    2: 'moderate',
    3: 'considerable',
    4: 'high',
    5: 'very_high',
}

# the typical avalanche situations (STABILITE/SitAvalTyp @SAT1, @SAT2), as
# the bra.xslt of Météo-France names them
AVALANCHE_PROBLEMS = {
    1: 'new_snow',
    2: 'wind_slab',
    3: 'persistent_weak_layers',
    4: 'wet_snow',
    5: 'gliding_snow',
    6: 'no_distinct_avalanche_problem',
}

ASPECTS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']

# the wind directions are in French (O: ouest)
WIND_DIRECTIONS = {
    'N': 'N',
    'NE': 'NE',
    'E': 'E',
    'SE': 'SE',
    'S': 'S',
    'SO': 'SW',
    'O': 'W',
    'NO': 'NW',
}


class InvalidBulletin(ValueError):
    """The XML is not a well-formed BRA, lacks its massif or dates, or has entities."""


def bra_to_caaml(xml):
    """Return the CAAML bulletins of a BRA: an empty list without a bulletin."""
    try:
        root = fromstring(xml)
    except (ParseError, DefusedXmlException) as e:
        raise InvalidBulletin(str(e)) from e
    # the massif of Andorra answers a <message> pointing to its own service
    if root.tag != 'BULLETINS_NEIGE_AVALANCHE':
        return {'bulletins': []}
    try:
        return {'bulletins': [_bulletin(root)]}
    except (AttributeError, TypeError, ValueError) as e:
        # a missing or odd attribute: the massif, the dates...
        raise InvalidBulletin(f'unexpected BRA: {e!r}') from e


def _bulletin(root):
    region_id = 'FR-' + root.get('ID').zfill(2)
    start = _time(root.get('DATEBULLETIN'))
    risk = root.find('CARTOUCHERISQUE/RISQUE')
    return _compact(
        {
            'bulletinID': f'{region_id}_{start.isoformat()}',
            'lang': 'fr',
            'publicationTime': _iso(
                root.get('DATEDIFFUSION') or root.get('DATEBULLETIN')
            ),
            'validTime': {
                'startTime': start.isoformat(),
                'endTime': _time(root.get('DATEVALIDITE')).isoformat(),
            },
            'unscheduled': root.get('AMENDEMENT') == 'true',
            'source': {'provider': PROVIDER},
            'regions': [{'regionID': region_id, 'name': root.get('MASSIF')}],
            'dangerRatings': _danger_ratings(risk),
            'avalancheProblems': _avalanche_problems(root.find('STABILITE/SitAvalTyp')),
            'avalancheActivity': _texts(
                _text(root, 'STABILITE/TITRE'),
                _text(root, 'STABILITE/TEXTESANSTITRE')
                or _text(root, 'STABILITE/TEXTE'),
            ),
            'snowpackStructure': _texts(None, _text(root, 'QUALITE/TEXTE')),
            'weatherForecast': _texts(None, _text(root, 'METEO/COMMENTAIRE')),
            'tendency': _tendency(root, risk),
            'customData': {
                # the day the bulletin is valid for, as in the EAWS bulletins
                'ALBINA': {'mainDate': _date(root.get('DATEVALIDITE'))},
                'MeteoFrance': _meteofrance(root, risk),
            },
        }
    )


def _danger_ratings(risk):
    # up to two elevation bands (RISQUE1 below LOC1, RISQUE2 above LOC2), whose
    # danger may change in the afternoon (EVOLURISQUE1, EVOLURISQUE2)
    if risk is None:
        return []
    bands = [
        (risk.get(f'RISQUE{i}'), risk.get(f'LOC{i}'), risk.get(f'EVOLURISQUE{i}'))
        for i in (1, 2)
    ]
    bands = [band for band in bands if band[0]]
    if any(evolution for _, _, evolution in bands):
        periods = [('earlier', False), ('later', True)]
    else:
        periods = [('all_day', False)]
    ratings = []
    for period, later in periods:
        for value, location, evolution in bands:
            rating = {
                'mainValue': _danger(evolution if later and evolution else value),
                'validTimePeriod': period,
            }
            elevation = _elevation(location)
            if elevation:
                rating['elevation'] = elevation
            ratings.append(rating)
    return ratings


def _elevation(location):
    # '<2200': below 2200 m, '>2200': above
    if not location:
        return None
    bound = 'upperBound' if location.startswith('<') else 'lowerBound'
    return {bound: location.lstrip('<>')}


def _avalanche_problems(situations):
    if situations is None:
        return []
    problems = []
    for name in ('SAT1', 'SAT2'):
        problem = AVALANCHE_PROBLEMS.get(_int(situations.get(name)))
        if problem and problem not in problems:
            problems.append(problem)
    return [{'problemType': problem} for problem in problems]


def _tendency(root, risk):
    if (
        risk is None
        or not _int(risk.get('RISQUEMAXIJ2'))
        or not risk.get('DATE_RISQUE_J2')
    ):
        return []
    later = _int(risk.get('RISQUEMAXIJ2'))
    today = _int(risk.get('RISQUEMAXI'))
    start = _time(risk.get('DATE_RISQUE_J2'))
    tendency = {
        'validTime': {
            'startTime': start.isoformat(),
            'endTime': (start + timedelta(days=1)).isoformat(),
        },
        'customData': {'MeteoFrance': {'maxDangerRating': _danger(later)}},
    }
    if today:
        tendency['tendencyType'] = (
            'increasing'
            if later > today
            else 'decreasing'
            if later < today
            else 'steady'
        )
    texts = _texts(
        _text(root, 'CARTOUCHERISQUE/RisqueJ2'),
        _text(root, 'CARTOUCHERISQUE/CommentaireRisqueJ2'),
    )
    return [{**tendency, **(texts or {})}]


def _meteofrance(root, risk):
    risk = risk.attrib if risk is not None else {}
    slopes = root.find('CARTOUCHERISQUE/PENTE')
    slopes = slopes.attrib if slopes is not None else {}
    history = root.find('BSH')
    return _compact(
        {
            'headline': _text(root, 'CARTOUCHERISQUE/AVIS'),
            'maxDangerRating': _danger(risk['RISQUEMAXI'])
            if 'RISQUEMAXI' in risk
            else None,
            'elevationThreshold': _int(risk.get('ALTITUDE')),
            'dangerComment': (risk.get('COMMENTAIRE') or '').strip() or None,
            # the most dangerous aspects
            'avalancheProneLocation': _compact(
                {
                    'aspects': [
                        aspect for aspect in ASPECTS if slopes.get(aspect) == 'true'
                    ],
                    'comment': (slopes.get('COMMENTAIRE') or '').strip() or None,
                }
            ),
            'naturalAvalanches': _text(root, 'CARTOUCHERISQUE/NATUREL'),
            'triggeredAvalanches': _text(root, 'CARTOUCHERISQUE/ACCIDENTEL'),
            'snowCover': _snow_cover(root.find('ENNEIGEMENT')),
            'newSnow': _new_snow(root.find('NEIGEFRAICHE')),
            'weather': _weather(root.find('METEO')),
            # the last 7 days
            'history': _compact(
                {
                    'maxDangerRatings': [
                        {
                            'date': _date(r.get('DATE')),
                            'value': _danger(r.get('RISQUEMAXI')),
                        }
                        for r in history.findall('RISQUES/RISQUE')
                    ],
                    'snowCover': [
                        _snow_cover(cover)
                        for cover in history.findall('ENNEIGEMENTS/ENNEIGEMENT')
                    ],
                    'newSnow': _new_snow(history.find('NEIGEFRAICHE')),
                }
            )
            if history is not None
            else None,
        }
    )


def _snow_cover(cover):
    # the snow depth (cm) on north and south slopes at a few elevations, and the
    # elevation (m) of the lower limit of the snow cover
    if cover is None:
        return None
    return _compact(
        {
            'date': _date(cover.get('DATE')),
            'limitNorth': _int(cover.get('LimiteNord')),
            'limitSouth': _int(cover.get('LimiteSud')),
            'levels': [
                {
                    'elevation': _int(level.get('ALTI')),
                    'north': _int(level.get('N')),
                    'south': _int(level.get('S')),
                }
                for level in cover.findall('NIVEAU')
            ],
        }
    )


def _new_snow(new_snow):
    # the fresh snow (cm) in 24 h at an elevation, and the precipitation (mm)
    if new_snow is None:
        return None
    return _compact(
        {
            'elevation': _int(new_snow.get('ALTITUDESS')),
            'days': [
                _compact(
                    {
                        'date': _date(day.get('DATE')),
                        'min': _int(day.get('SS24Min')),
                        'max': _int(day.get('SS24Max')),
                        'precipitation': _int(day.get('RR24')),
                    }
                )
                for day in new_snow.findall('NEIGE24H')
            ],
        }
    )


def _weather(weather):
    # the wind at two elevations, the 0 °C isotherm and the rain-snow limit (m),
    # every 6 hours; -1 when not given
    if weather is None:
        return None
    return _compact(
        {
            'windElevations': [
                _measure(weather.get('ALTITUDEVENT1')),
                _measure(weather.get('ALTITUDEVENT2')),
            ],
            'forecasts': [
                _compact(
                    {
                        'time': _iso(forecast.get('DATE')),
                        'wind': [
                            {
                                'direction': WIND_DIRECTIONS.get(
                                    forecast.get(f'DD{i}')
                                ),
                                'speed': _measure(forecast.get(f'FF{i}')),
                            }
                            for i in (1, 2)
                        ],
                        'freezingLevel': _measure(forecast.get('ISO0')),
                        'rainSnowLimit': _measure(forecast.get('PLUIENEIGE')),
                        # the code of Météo-France's weather icon
                        'weatherCode': _measure(forecast.get('TEMPSSENSIBLE')),
                    }
                )
                for forecast in weather.findall('ECHEANCE')
            ],
        }
    )


def _texts(highlights, comment):
    texts = _compact({'highlights': highlights, 'comment': comment})
    return texts or None


def _text(root, path):
    element = root.find(path)
    if element is None or not element.text:
        return None
    return _paragraphs(element.text) or None


def _paragraphs(text):
    # the texts of Météo-France glue their sections together ("lourde.Départs
    # spontanés :") and mark the items of a list with a star
    text = GLUED_SENTENCES.sub(r'\1\n', text)
    text = SECTIONS.sub('\n', text)
    text = LIST_ITEMS.sub('\n• ', text)
    lines = (' '.join(line.split()) for line in text.splitlines())
    return '\n'.join(line for line in lines if line)


def _danger(value):
    return DANGER_RATINGS.get(_int(value), 'no_rating')


def _int(value):
    try:
        return int(value)
    except TypeError, ValueError:
        return None


def _measure(value):
    value = _int(value)
    return value if value is not None and value >= 0 else None


def _time(value):
    # the times are local times of Paris, without offset
    time = datetime.fromisoformat(value)
    return time if time.tzinfo else time.replace(tzinfo=PARIS)


def _iso(value):
    return _time(value).isoformat() if value else None


def _date(value):
    return value[:10] if value else None


def _compact(values):
    return {key: value for key, value in values.items() if value not in (None, [], {})}
