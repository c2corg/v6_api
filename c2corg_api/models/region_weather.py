from sqlalchemy import (
    REAL,
    Boolean,
    Column,
    DateTime,
    SmallInteger,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB

from c2corg_api.models import Base, schema


class RegionWeatherHour(Base):
    """The weather of a region at an hour: observed, or forecast."""

    # From the bulletins of SLF for now (customData.CH.weather, out of the
    # stored CAAML), maybe from weather stations later. The latest
    # publication wins: a forecast hour becomes an observed one.

    __tablename__ = 'region_weather_hours'

    region_id = Column(Text, primary_key=True)
    time = Column(DateTime(timezone=True), primary_key=True)
    provider = Column(Text, nullable=False)
    temperature_c = Column(REAL)
    temperature_elevation_m = Column(SmallInteger)
    snowfall_limit_m = Column(SmallInteger)
    # why there is no limit (SLF: BELOW_REGION, ABOVE_REGION...)
    snowfall_limit_null_reason = Column(Text)
    is_forecast = Column(Boolean, nullable=False)
    publication_time = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = ({'schema': schema},)


class RegionWeatherPeriod(Base):
    """The wind and the new snow of a region over a period (a day, 16:00 UTC)."""

    __tablename__ = 'region_weather_periods'

    region_id = Column(Text, primary_key=True)
    period_start = Column(DateTime(timezone=True), primary_key=True)
    period_end = Column(DateTime(timezone=True), nullable=False)
    provider = Column(Text, nullable=False)
    wind_speed_kmh = Column(SmallInteger)
    wind_direction = Column(Text)
    # SLF: how remarkable it is (medium, high...)
    wind_highlight = Column(Text)
    # [{snowCm, elevationM, precipitationType?, highlight?}], as given
    new_snow = Column(JSONB, nullable=False)
    is_forecast = Column(Boolean, nullable=False)
    publication_time = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = ({'schema': schema},)
