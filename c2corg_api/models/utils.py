from geoalchemy2 import WKBElement, shape as ga_shape
from shapely.geometry import LineString, MultiLineString
from shapely.ops import transform
from sqlalchemy.dialects import postgresql
import sqlalchemy as sa
from sqlalchemy.sql.expression import and_
from sqlalchemy.sql.functions import func
import re


def copy_attributes(obj_from, obj_to, attributes):
    """
    Copies the given attributes from `obj_from` to `obj_to` (shallow copy).
    """
    for attribute in attributes:
        if hasattr(obj_from, attribute):
            current_val = getattr(obj_to, attribute)
            new_val = getattr(obj_from, attribute)

            # To make the SQLAlchemy check if a document has changed work
            # properly, we only copy an attribute if the value has changed.
            # For geometries, we always copy the value.
            if isinstance(current_val, WKBElement) or \
                    isinstance(new_val, WKBElement) or \
                    current_val != new_val:
                setattr(obj_to, attribute, new_val)


class ArrayOfEnum(postgresql.ARRAY):
    """
    SQLAlchemy type for an array of enums.
    http://docs.sqlalchemy.org/en/latest/dialects/postgresql.html#postgresql-array-of-enum
    """

    def bind_expression(self, bindvalue):
        return sa.cast(bindvalue, self)

    def result_processor(self, dialect, coltype):
        super_rp = super(ArrayOfEnum, self).result_processor(
            dialect, coltype)

        def handle_raw_string(value):
            if value == '{}':
                return []
            else:
                inner = re.match(r"^{(.*)}$", value).group(1)
                return inner.split(",")

        def process(value):
            if value is None:
                return None
            return super_rp(handle_raw_string(value))
        return process


def extend_dict(d1, d2):
    """Update `d1` with the entries of `d2` and return `d1`.
    """
    d1.update(d2)
    return d1


def get_mid_point(wkb_track):
    """Get the point in the middle of a track. If the track is a
    MultiLineString the point in the middle of the first line is taken.
    """
    track = wkb_to_shape(wkb_track)

    if isinstance(track, LineString):
        mid_point = track.interpolate(0.5, True)
    elif isinstance(track, MultiLineString) and track.geoms:
        mid_point = track.geoms[0].interpolate(0.5, True)
    else:
        return None

    return ga_shape.from_shape(mid_point, srid=3857)


def wkb_to_shape(wkb_element):
    """ Create a 2D Shapely shape from a WKB value. 3D and 4D geometries
     are turned into 2D geometries.
    """
    assert (isinstance(wkb_element, WKBElement))
    geom = ga_shape.to_shape(wkb_element)
    return _force_2d_shapely(geom)


def _force_2d_shapely(geom):
    """Strip Z/M dimensions from a Shapely geometry."""
    if geom.has_z:
        return transform(lambda x, y, z=None: (x, y), geom)
    return geom


def windowed_query(q, column, windowsize):
    """"Break a Query into windows on a given column.
    Source: https://bitbucket.org/zzzeek/sqlalchemy/wiki/UsageRecipes/WindowedRangeQuery  # noqa

    If the query does not use eager loading `yield_per` can be used instead for
    native streaming.
    """

    for whereclause in column_windows(
            q.session,
            column, windowsize):
        for row in q.filter(whereclause).order_by(column):
            yield row


def column_windows(session, column, windowsize):
    """Return a series of WHERE clauses against
    a given column that break it into windows.

    Result is an iterable of tuples, consisting of
    ((start, end), whereclause), where (start, end) are the ids.

    Requires a database that supports window functions,
    i.e. Postgresql, SQL Server, Oracle.

    Enhance this yourself !  Add a "where" argument
    so that windows of just a subset of rows can
    be computed.

    Source: https://bitbucket.org/zzzeek/sqlalchemy/wiki/UsageRecipes/WindowedRangeQuery  # noqa
    """
    def int_for_range(start_id, end_id):
        if end_id:
            return and_(
                column >= start_id,
                column < end_id
            )
        else:
            return column >= start_id

    q = session.query(
        column,
        func.row_number().over(order_by=column).label('rownum')
    ). \
        from_self(column)
    if windowsize > 1:
        q = q.filter(sa.text("rownum %% %d=1" % windowsize))

    intervals = [id for id, in q]

    while intervals:
        start = intervals.pop(0)
        if intervals:
            end = intervals[0]
        else:
            end = None
        yield int_for_range(start, end)
