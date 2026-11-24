"""The weather of the regions given with the bulletins (SLF), in PostgreSQL."""
# SLF gives the weather of each micro-region (customData.CH.weather): the
# 2 days before and the forecast day, temperature and snowfall limit by
# hour, wind and new snow by day. The same in every language: stored once,
# out of the CAAML (13 of the 17 kB of a bulletin), not answered with it.

from datetime import datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from c2corg_api.avalanche_bulletins.cache import CET
from c2corg_api.models.region_weather import RegionWeatherHour, RegionWeatherPeriod


def extract(bulletin):
    """Return the bulletin without its weather, and the weather (None without)."""
    custom = bulletin.get('customData') or {}
    slf = custom.get('CH')
    if not isinstance(slf, dict) or 'weather' not in slf:
        return bulletin, None
    without = {key: value for key, value in slf.items() if key != 'weather'}
    return {**bulletin, 'customData': {**custom, 'CH': without}}, slf['weather']


def save(session, provider, region_ids, publication_time, weather):
    """Store the weather of regions, unless as late a publication did."""
    # forecast: what was not over when published
    hours, periods = {}, []
    for period in weather or []:
        start = _time(period['period']['start'])
        end = _time(period['period']['end'])
        wind = period.get('wind') or {}
        periods.append(
            {
                'period_start': start,
                'period_end': end,
                'wind_speed_kmh': wind.get('speedKmh'),
                'wind_direction': wind.get('direction'),
                'wind_highlight': wind.get('highlight'),
                'new_snow': period.get('newSnow') or [],
                'is_forecast': end > publication_time,
            }
        )
        series = period.get('timeSeries') or {}
        for value in series.get('temperatures') or []:
            hour = _hour(hours, value['timestamp'], publication_time)
            hour['temperature_c'] = value.get('valueC')
            hour['temperature_elevation_m'] = value.get('elevationM')
        for value in series.get('snowfallLimit') or []:
            hour = _hour(hours, value['timestamp'], publication_time)
            hour['snowfall_limit_m'] = value.get('elevationM')
            hour['snowfall_limit_null_reason'] = value.get('reasonForNull')
    common = {'provider': provider, 'publication_time': publication_time}
    for model, rows, key in (
        (RegionWeatherPeriod, periods, 'period_start'),
        (RegionWeatherHour, list(hours.values()), 'time'),
    ):
        if not rows:
            continue
        for region_id in region_ids:
            insertion = insert(model).values(
                [{**row, **common, 'region_id': region_id} for row in rows]
            )
            excluded = insertion.excluded
            names = {name for row in rows for name in row} | set(common)
            session.execute(
                insertion.on_conflict_do_update(
                    index_elements=['region_id', key],
                    set_={name: excluded[name] for name in names - {key}},
                    # the other languages of the publication change nothing
                    where=model.publication_time < excluded.publication_time,
                )
            )


def weather(session, region_id, date_from, date_to):
    """Return the weather of a (micro-)region over days (both included)."""
    start = datetime.combine(date_from, time(), tzinfo=CET)
    end = datetime.combine(date_to + timedelta(days=1), time(), tzinfo=CET)
    hours = session.scalars(
        select(RegionWeatherHour)
        .where(
            RegionWeatherHour.region_id == region_id,
            RegionWeatherHour.time >= start,
            RegionWeatherHour.time < end,
        )
        .order_by(RegionWeatherHour.time)
    )
    periods = session.scalars(
        select(RegionWeatherPeriod)
        .where(
            RegionWeatherPeriod.region_id == region_id,
            RegionWeatherPeriod.period_end > start,
            RegionWeatherPeriod.period_start < end,
        )
        .order_by(RegionWeatherPeriod.period_start)
    )
    return {
        'hours': [
            {
                'time': h.time.isoformat(),
                'temperatureC': h.temperature_c,
                'temperatureElevationM': h.temperature_elevation_m,
                'snowfallLimitM': h.snowfall_limit_m,
                'snowfallLimitNullReason': h.snowfall_limit_null_reason,
                'forecast': h.is_forecast,
            }
            for h in hours
        ],
        'periods': [
            {
                'start': p.period_start.isoformat(),
                'end': p.period_end.isoformat(),
                'wind': {
                    'speedKmh': p.wind_speed_kmh,
                    'direction': p.wind_direction,
                    'highlight': p.wind_highlight,
                },
                'newSnow': p.new_snow,
                'forecast': p.is_forecast,
            }
            for p in periods
        ],
    }


def _hour(hours, timestamp, publication_time):
    hour = _time(timestamp)
    # all the columns in each row: one INSERT of many rows
    return hours.setdefault(
        hour,
        {
            'time': hour,
            'temperature_c': None,
            'temperature_elevation_m': None,
            'snowfall_limit_m': None,
            'snowfall_limit_null_reason': None,
            'is_forecast': hour > publication_time,
        },
    )


def _time(value):
    return datetime.fromisoformat(value)
