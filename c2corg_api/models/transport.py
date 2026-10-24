from geoalchemy2.types import Geometry
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from c2corg_api.models import Base, schema


class TransportFeed(Base):
    """A GTFS feed the public transport lines and stops are imported from."""

    __tablename__ = 'transport_feeds'
    __table_args__ = {'schema': schema, 'extend_existing': True}

    feed_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    url = Column(String, nullable=False)
    license = Column(String, nullable=False)
    attribution = Column(String, nullable=False)
    # checksum of the last imported archive, to skip unchanged feeds
    checksum = Column(String)
    imported_at = Column(DateTime(timezone=True))
    status = Column(String)


class TransportLine(Base):
    """A public transport line (GTFS route).

    A public transport line (GTFS route), drawn with its merged and
    simplified path.
    """

    __tablename__ = 'transport_lines'
    __table_args__ = {'schema': schema, 'extend_existing': True}

    line_id = Column(Integer, primary_key=True)
    feed_id = Column(
        String, ForeignKey(schema + '.transport_feeds.feed_id'), nullable=False
    )
    route_id = Column(String, nullable=False)
    short_name = Column(String, nullable=False)
    long_name = Column(String, nullable=False)
    mode = Column(String, nullable=False)
    color = Column(String)
    text_color = Column(String)
    operator = Column(String)
    url = Column(String)
    geom = Column(Geometry('MULTILINESTRING', srid=3857))
    # the line this one is a duplicate of (the same line in another feed):
    # hidden, see c2corg_api.transport.dedup
    duplicate_of = Column(Integer)
    # directions, ordered stops and timetables, only read on click
    details = Column(JSONB, nullable=False)


class TransportStop(Base):
    """A public transport stop (GTFS stop, or its parent station).

    A public transport stop (GTFS stop, or its parent station) with the
    timetable of the lines serving it.
    """

    __tablename__ = 'transport_stops'
    __table_args__ = {'schema': schema, 'extend_existing': True}

    stop_pk = Column(Integer, primary_key=True)
    feed_id = Column(
        String, ForeignKey(schema + '.transport_feeds.feed_id'), nullable=False
    )
    stop_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    mode = Column(String, nullable=False)
    geom = Column(Geometry('POINT', srid=3857), nullable=False)
    ref_ids = Column(ARRAY(String), nullable=False, default=list)
    navitia_ids = Column(ARRAY(String), nullable=False, default=list)
    # the stop that is the anchor of the cluster of stops of the same place
    # (itself for an anchor), see c2corg_api.transport.dedup
    cluster_id = Column(Integer)
    # lines and departures, only read on click
    details = Column(JSONB, nullable=False)
