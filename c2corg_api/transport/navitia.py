"""Planned timetables of the public transport, read from Navitia.

Navitia is paid per request, so everything here is meant to be cached by the
caller: the functions take a ``cached(kind, key, creator)`` callable, and the
number of requests made in a day can be capped (``budget``).

Only the planned timetables are asked for (``data_freshness=base_schedule``):
real time is not needed to know whether a line runs.
"""

import datetime
import logging
import os
import re
import unicodedata
import zoneinfo
from urllib.parse import quote

import requests

log = logging.getLogger(__name__)

BASE_URL = 'https://api.navitia.io/v1'
TIMEOUT = 20

# a stop of the map and the stop area of Navitia are at most this far apart (meters)
STOP_AREA_DISTANCE = 100
# a click on a line is at most this far from one of the stops of the line (meters)
LINE_STOP_DISTANCE = 1500
# stop areas tried to identify a line
MAX_STOP_AREAS_FOR_A_LINE = 3

SEARCH_DAYS = 30

# Navitia marks the trips that run on demand (to book beforehand) with these
ON_DEMAND_STOP_TIME = 'on_demand_transport'
ON_DEMAND_TRIP_PREFIX = 'odt'


class NavitiaError(Exception):
    """A failure with a HTTP status and a short code, for the API to answer with."""

    def __init__(self, status, code):
        super().__init__(code)
        self.status = status
        self.code = code


def paris_today():
    """Today in Paris: the day of the timetables of the lines of the Alps."""
    return datetime.datetime.now(zoneinfo.ZoneInfo('Europe/Paris')).date()


class DailyBudget:
    """Caps the number of requests sent to Navitia each day.

    ``counter`` increments a number by day and returns the new value (see
    views/transport.py, it lives in Redis). Without counter, nothing is capped.
    """

    def __init__(self, limit, counter=None, today=paris_today):
        self.limit = limit
        self.counter = counter
        self.today = today

    def consume(self):
        if not self.limit or self.counter is None:
            return
        try:
            used = self.counter(self.today().isoformat())
        except Exception:
            # a counter that is down must not stop the timetables
            log.warning('Navitia request counter failed', exc_info=True)
            return
        if used > self.limit:
            raise NavitiaError(429, 'daily_budget_reached')


budget = DailyBudget(limit=0)


def get_json(path, params=None):
    """One request to Navitia."""
    api_key = os.getenv('NAVITIA_API_KEY')
    if not api_key:
        raise NavitiaError(500, 'navitia_not_configured')
    budget.consume()
    try:
        response = requests.get(
            BASE_URL + path,
            params=params,
            headers={'Authorization': api_key},
            timeout=TIMEOUT,
        )
    except requests.exceptions.RequestException as error:
        log.warning('Navitia request failed: %s', error)
        raise NavitiaError(504, 'navitia_unavailable') from error
    if response.status_code == 404:
        raise NavitiaError(404, 'unknown_object')
    if response.status_code == 400:
        raise NavitiaError(400, 'invalid_param')
    if not response.ok:
        log.warning('Navitia answered %s on %s', response.status_code, path)
        raise NavitiaError(502, 'navitia_error')
    return response.json()


def normalize(text):
    """Lower case letters and digits only: to compare names written differently."""
    decomposed = unicodedata.normalize('NFKD', text or '')
    letters = ''.join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', '', letters.lower())


def parse_date_time(value):
    """'20261026T060500' as (date, 'HH:MM'), or None."""
    match = re.fullmatch(r'(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})\d{2}', value or '')
    if not match:
        return None
    year, month, day, hour, minute = (int(group) for group in match.groups())
    try:
        return datetime.date(year, month, day), f'{hour:02d}:{minute:02d}'
    except ValueError:
        return None


def navitia_date(date):
    return date.strftime('%Y%m%dT000000')


def region_of(lon, lat, cached):
    """Navitia coverage of a point (fr-se, ch, it...), kept for a long time."""
    key = f'{lon:.2f};{lat:.2f}'

    def create():
        regions = get_json(f'/coord/{lon};{lat}').get('regions') or []
        if not regions:
            raise NavitiaError(404, 'no_coverage')
        return regions[0]

    return cached('region', key, create)


def find_stop_areas(lon, lat, distance, count, cached):
    """Stop areas around a point, nearest first."""
    key = f'{lon:.4f};{lat:.4f};{distance};{count}'

    def create():
        data = get_json(
            f'/coord/{lon};{lat}/places_nearby',
            {'type[]': 'stop_area', 'distance': distance, 'count': count},
        )
        places = [
            place for place in data.get('places_nearby', []) if place.get('stop_area')
        ]
        places.sort(key=lambda place: float(place.get('distance') or 0))
        return [
            {
                'id': place['id'],
                'name': place['stop_area'].get('name') or place.get('name'),
                'lon': float(place['stop_area']['coord']['lon']),
                'lat': float(place['stop_area']['coord']['lat']),
                'distance': float(place.get('distance') or 0),
            }
            for place in places
        ]

    return cached('nearby', key, create)


def pick_stop_area(candidates, name=None):
    """Pick the stop area named like the stop of the map, else the nearest."""
    wanted = normalize(name)
    if wanted:
        for candidate in candidates:
            if normalize(candidate['name']) == wanted:
                return candidate
    return candidates[0] if candidates else None


def stop_schedules(region, stop_area_id, date, days=1, per_schedule=300):
    return get_json(
        f'/coverage/{region}/stop_areas/{quote(stop_area_id)}/stop_schedules',
        {
            'from_datetime': navitia_date(date),
            'duration': 86400 * days,
            'data_freshness': 'base_schedule',
            'items_per_schedule': per_schedule,
            'count': 50,
        },
    )


def parse_stop_schedules(data, date):
    """Read the lines of a stop with their departures of the day, as 'HH:MM'."""
    lines = []
    for schedule in data.get('stop_schedules', []):
        info = schedule.get('display_informations') or {}
        route = schedule.get('route') or {}
        line = route.get('line') or {}
        times = []
        on_demand = []
        for date_time in schedule.get('date_times', []):
            parsed = parse_date_time(date_time.get('date_time'))
            if parsed and parsed[0] == date:
                times.append(parsed[1])
                if ON_DEMAND_STOP_TIME in (
                    date_time.get('additional_informations') or []
                ):
                    on_demand.append(parsed[1])
        lines.append(
            {
                'line_id': line.get('id'),
                'route_id': route.get('id'),
                'code': info.get('code') or info.get('label'),
                'name': info.get('name'),
                'color': info.get('color'),
                'text_color': info.get('text_color'),
                'network': info.get('network'),
                'mode': info.get('commercial_mode'),
                'direction': info.get('direction'),
                'departures': sorted(set(times)),
                'on_demand': sorted(set(on_demand)),
            }
        )
    lines.sort(key=lambda line: (not line['departures'], line['code'] or ''))
    return lines


def next_running_date(data, after):
    """First day after `after` with a departure, in a wide search of stop_schedules."""
    dates = set()
    for schedule in data.get('stop_schedules', []):
        for date_time in schedule.get('date_times', []):
            parsed = parse_date_time(date_time.get('date_time'))
            if parsed and parsed[0] > after:
                dates.add(parsed[0])
    return min(dates).isoformat() if dates else None


def stop_timetable(lon, lat, date, cached, navitia_id=None, name=None):
    """Departures of a stop on a day, or None if Navitia knows no stop there."""
    region = region_of(lon, lat, cached)
    if navitia_id:
        stop_area = {'id': navitia_id, 'name': name, 'lon': lon, 'lat': lat}
    else:
        stop_area = pick_stop_area(
            find_stop_areas(lon, lat, STOP_AREA_DISTANCE, 5, cached), name
        )
        if not stop_area:
            return None

    def create():
        lines = parse_stop_schedules(
            stop_schedules(region, stop_area['id'], date), date
        )
        next_date = None
        if not any(line['departures'] for line in lines):
            wide = stop_schedules(
                region, stop_area['id'], date, days=SEARCH_DAYS, per_schedule=1
            )
            next_date = next_running_date(wide, date)
        return {
            'stop_area': stop_area,
            'date': date.isoformat(),
            'lines': lines,
            'next_date': next_date,
        }

    return cached('stop', f'{region}|{stop_area["id"]}|{date}', create)


def same_line(schedule, ref):
    info = schedule.get('display_informations') or {}
    codes = {normalize(info.get('code')), normalize(info.get('label'))}
    return normalize(ref) in codes - {''}


def words(text):
    decomposed = unicodedata.normalize('NFKD', text or '')
    letters = ''.join(c for c in decomposed if not unicodedata.combining(c))
    return set(re.findall(r'[a-z0-9]{3,}', letters.lower()))


def network_overlap(left, right):
    """How many words two network names have in common."""
    return len(words(left) & words(right))


def find_line(lon, lat, ref, network, date, cached):
    """Find the Navitia line numbered `ref` that serves the area around a point."""
    region = region_of(lon, lat, cached)
    key = f'{region}|{lon:.3f};{lat:.3f}|{normalize(ref)}|{normalize(network)}'

    def create():
        candidates = find_stop_areas(lon, lat, LINE_STOP_DISTANCE, 10, cached)
        best = None
        for stop_area in candidates[:MAX_STOP_AREAS_FOR_A_LINE]:
            data = stop_schedules(region, stop_area['id'], date, per_schedule=1)
            for schedule in data.get('stop_schedules', []):
                if not same_line(schedule, ref):
                    continue
                info = schedule.get('display_informations') or {}
                line = (schedule.get('route') or {}).get('line') or {}
                score = network_overlap(network, info.get('network'))
                if line.get('id') and (best is None or score > best[0]):
                    best = (score, line['id'], info)
            if best:
                break
        if not best:
            return None
        return {'line_id': best[1], 'name': best[2].get('name')}

    return cached('line', key, create)


def parse_route_schedules(data, date):
    """Each direction of a line: its stops and, per trip, the times of the day."""
    directions = []
    stop_area_ids = []
    for schedule in data.get('route_schedules', []):
        table = schedule.get('table') or {}
        rows = table.get('rows') or []
        stops = []
        for row in rows:
            stop_point = row.get('stop_point') or {}
            stop_area = (stop_point.get('stop_area') or {}).get('id')
            stops.append(
                {
                    'id': stop_point.get('id'),
                    'name': stop_point.get('name'),
                    'stop_area_id': stop_area,
                }
            )
            if stop_area and stop_area not in stop_area_ids:
                stop_area_ids.append(stop_area)
        trip_count = max(
            [len(table.get('headers') or [])]
            + [len(row.get('date_times') or []) for row in rows]
        )
        headers = table.get('headers') or []
        trips = []
        for index in range(trip_count):
            times = []
            on_demand = False
            for row in rows:
                date_times = row.get('date_times') or []
                date_time = date_times[index] if index < len(date_times) else {}
                parsed = parse_date_time(date_time.get('date_time'))
                times.append(parsed[1] if parsed and parsed[0] == date else None)
                if ON_DEMAND_STOP_TIME in (
                    date_time.get('additional_informations') or []
                ):
                    on_demand = True
            header = headers[index] if index < len(headers) else {}
            if any(
                info.startswith(ON_DEMAND_TRIP_PREFIX)
                for info in header.get('additional_informations') or []
            ):
                on_demand = True
            if any(times):
                trips.append({'times': times, 'on_demand': on_demand})
        info = schedule.get('display_informations') or {}
        directions.append(
            {
                'direction': info.get('direction'),
                'stops': stops,
                'trips': trips,
            }
        )
    return directions, stop_area_ids


def route_schedules(region, line_id, date, days=1, per_schedule=300):
    return get_json(
        f'/coverage/{region}/lines/{quote(line_id)}/route_schedules',
        {
            'from_datetime': navitia_date(date),
            'duration': 86400 * days,
            'data_freshness': 'base_schedule',
            'items_per_schedule': per_schedule,
        },
    )


def line_timetable(lon, lat, ref, network, date, cached):
    """Timetable of a line on a day, or None if Navitia does not know the line."""
    line = find_line(lon, lat, ref, network, date, cached)
    if not line:
        return None
    region = region_of(lon, lat, cached)

    def create():
        directions, stop_area_ids = parse_route_schedules(
            route_schedules(region, line['line_id'], date), date
        )
        next_date = None
        if not any(direction['trips'] for direction in directions):
            wide = route_schedules(
                region, line['line_id'], date, days=SEARCH_DAYS, per_schedule=1
            )
            next_date = next_route_date(wide, date)
        return {
            'line': line,
            'date': date.isoformat(),
            'directions': directions,
            'stop_area_ids': stop_area_ids,
            'next_date': next_date,
        }

    return cached('line_timetable', f'{region}|{line["line_id"]}|{date}', create)


def next_route_date(data, after):
    """First day after `after` with a trip in a wide search of route_schedules."""
    dates = set()
    for schedule in data.get('route_schedules', []):
        for row in (schedule.get('table') or {}).get('rows') or []:
            for date_time in row.get('date_times') or []:
                parsed = parse_date_time(date_time.get('date_time'))
                if parsed and parsed[0] > after:
                    dates.add(parsed[0])
    return min(dates).isoformat() if dates else None
