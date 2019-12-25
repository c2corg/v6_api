import logging
import math

import pyproj
import re
from c2corg_api.models.outing import OUTING_TYPE
from c2corg_api.models.xreport import XREPORT_TYPE
from c2corg_api.search.mapping_types import reserved_query_fields
from functools import partial

from c2corg_api.search import create_search, search_documents, \
    get_text_query_on_title
from elasticsearch_dsl.query import Range, Term, Terms, Bool, GeoBoundingBox, \
    Exists

log = logging.getLogger(__name__)


def build_query(url_params, meta_params, doc_type):
    """Creates an ElasticSearch query from query parameters.
    """
    search_term = url_params.get('q', '').strip()
    limit = meta_params.get('limit')
    offset = meta_params.get('offset')

    search = create_search(doc_type)
    if search_term:
        search = search.query(
            get_text_query_on_title(search_term, meta_params.get('lang')))

    search_model = search_documents[doc_type]
    for param in url_params:
        if param in reserved_query_fields:
            continue
        filter = create_filter(param, url_params.get(param), search_model)
        if filter:
            search = search.filter(filter)

    # TODO : not sure of that, test it
    # search = search.\
        # fields([]).\
        # extra(from_=offset, size=limit)

    search = search.\
        extra(from_=offset, size=limit)

    if url_params.get('bbox'):
        bbox_filter = create_bbox_filter(url_params.get('bbox'))
        if bbox_filter:
            search = search.filter(bbox_filter)

    if not search_term:
        # if a search term is given, the documents are sorted by a relevance
        # score. if not explicitly sort by id/date.
        if doc_type == OUTING_TYPE:
            search = search.sort(
                {'date_end': {'order': 'desc'}}, {'id': {'order': 'desc'}})
        elif doc_type == XREPORT_TYPE:
            search = search.sort(
              {'date': {'order': 'desc'}}, {'id': {'order': 'desc'}})
        else:
            search = search.sort({'id': {'order': 'desc'}})

    log.debug('Search filter: {}'.format(search.to_dict()))

    return search


def create_filter(field_name, query_term, search_model):
    """Creates an ES filter for a search tuple (field_name, query_term), e.g.
    `('e', '1500,2500')` (which creates a range filter on the elevation field).
    """
    if field_name not in search_model.queryable_fields:
        return None
    if not query_term:
        return None

    field = search_model.queryable_fields.get(field_name)
    if hasattr(field, '_range') and field._range:
        return create_range_filter(field, query_term)
    elif hasattr(field, '_enum_range') and field._enum_range:
        return create_enum_range_filter(field, query_term)
    elif hasattr(field, '_enum_range_min_max') and field._enum_range_min_max:
        return create_enum_range_min_max_filter(field, query_term)
    elif hasattr(field, '_enum'):
        return create_term_filter(field, query_term)
    elif hasattr(field, '_is_bool') and field._is_bool:
        return create_boolean_filter(field, query_term)
    elif hasattr(field, '_is_id') and field._is_id:
        return create_id_filter(field, query_term)
    elif hasattr(field, '_date_range') and field._date_range:
        return create_date_range_filter(field, query_term)
    elif hasattr(field, '_date') and field._date:
        return create_date_filter(field, query_term)
    elif hasattr(field, '_integer_range') and field._integer_range:
        return create_number_range_filter(field, query_term)

    return None


def create_range_filter(field, query_term):
    """Creates an ElasticSearch range filter.

    E.g. the call `create_range_filter(elevation_field, '1500,2500') creates
    the following filter:
        {'range': {'elevation': {'gte': 1500, 'lte': 2500}}}
    """
    query_terms = query_term.split(',')
    range_values = list(map(parse_num, query_terms))

    n = len(range_values)
    range_from = range_values[0] if n > 0 else None
    range_to = range_values[1] if n > 1 else None

    if range_from is None and range_to is None:
        return None

    range_params = {}
    if range_from is not None and not math.isnan(range_from):
        range_params['gte'] = range_from
    if range_to is not None and not math.isnan(range_to):
        range_params['lte'] = range_to

    kwargs = {field._name: range_params}
    return Range(**kwargs)


def create_enum_range_filter(field, query_term):
    """Creates an ElasticSearch enum range filter.

    E.g. the call `create_enum_range_filter(quality, 'medium,great')
    creates the following filter:
        {'range': {'quality': {'gte': 2, 'lte': 4}}}
    """
    query_terms = query_term.split(',')
    map_enum = partial(map_enum_to_int, field._enum_mapper)
    range_values = list(map(map_enum, query_terms))

    n = len(range_values)
    range_from = range_values[0] if n > 0 else None
    range_to = range_values[1] if n > 1 else None

    if range_from is None and range_to is None:
        return None

    range_params = {}
    if range_from is not None:
        range_params['gte'] = range_from
    if range_to is not None:
        range_params['lte'] = range_to

    kwargs = {field._name: range_params}
    return Range(**kwargs)


def create_enum_range_min_max_filter(field, query_term):
    """Creates an ElasticSearch combined enum range filter.

    For example the fields `climbing_rating_min` and `climbing_rating_max` are
    combined into a single search field. Searching for `crat=4c,6b` returns
    the waypoints where the min/max climbing ratings match the given range.
    """
    query_terms = query_term.split(',')
    map_enum = partial(map_enum_to_int, field._enum_mapper)
    range_values = list(map(map_enum, query_terms))
    range_values = [t for t in range_values if t is not None]

    n = len(range_values)
    if n != 2:
        return None

    kwargs_start = {field.field_min: {'gt': range_values[1]}}
    kwargs_end = {field.field_max: {'lt': range_values[0]}}
    return Bool(must_not=Bool(should=[
        Range(**kwargs_start),
        Range(**kwargs_end),
        Bool(must=[
            ~Exists(field=field.field_min),
            ~Exists(field=field.field_max)
        ])
    ]))


def create_term_filter(field, query_term):
    """Creates an ElasticSearch term/terms filter for an enum field.
    """
    query_terms = query_term.split(',')
    term_values = list(
        map(partial(parse_enum_value, field._enum), query_terms))
    term_values = [t for t in term_values if t is not None]

    if not term_values:
        return None
    elif len(term_values) == 1:
        kwargs = {field._name: term_values[0]}
        return Term(**kwargs)
    else:
        kwargs = {field._name: term_values}
        return Terms(**kwargs)


def create_boolean_filter(field, query_term):
    """Creates an ElasticSearch term filter for a boolean field.
    """
    filter_value = None
    if query_term in ['true', 'True', '1']:
        filter_value = True
    elif query_term in ['false', 'False', '0']:
        filter_value = False

    if filter_value is None:
        return None
    else:
        kwargs = {field._name: filter_value}
        return Term(**kwargs)


def create_id_filter(field, query_term):
    """Creates an ElasticSearch term filter for a field, that contains
    document ids.
    """
    query_terms = query_term.split(',')
    term_values = list(map(parse_num, query_terms))
    term_values = [t for t in term_values if t is not None]

    if not term_values:
        return None
    elif len(term_values) == 1:
        kwargs = {field._name: term_values[0]}
        return Term(**kwargs)
    else:
        kwargs = {field._name: term_values}
        return Terms(**kwargs)


def create_date_range_filter(field, query_term):
    """Creates an ElasticSearch date-range filter.

    This filter type is currently only used for Outing.date_start/date_end.

    Valid query terms are:
        2016-01-01
        2016-01-01,2016-01-01
        2016-01-01,2016-01-03

    """
    query_terms = query_term.split(',')
    range_values = list(map(parse_date, query_terms))
    range_values = [t for t in range_values if t is not None]

    n = len(range_values)
    if n == 0:
        return None
    elif n == 1 or range_values[0] == range_values[1]:
        # single date
        kwargs_start = {field.field_date_start: {'lte': range_values[0]}}
        kwargs_end = {field.field_date_end: {'gte': range_values[0]}}
        return Bool(must=[
            Range(**kwargs_start),
            Range(**kwargs_end)
        ])
    else:
        # date range
        kwargs_start = {field.field_date_start: {'gt': range_values[1]}}
        kwargs_end = {field.field_date_end: {'lt': range_values[0]}}
        return Bool(must_not=Bool(should=[
            Range(**kwargs_start),
            Range(**kwargs_end)
        ]))


def create_date_filter(field, query_term):
    """Creates an ElasticSearch date-range filter for a single field.

    This filter type is currently only used for Image.date_time

    Valid query terms are:
        2016-01-01
        2016-01-01,2016-01-01
        2016-01-01,2016-01-03

    """
    query_terms = query_term.split(',')
    range_values = list(map(parse_date, query_terms))
    range_values = [t for t in range_values if t is not None]

    n = len(range_values)
    if n == 0:
        return None
    elif n == 1:
        range_values.append(range_values[0])

    kwargs = {
        field._field_date: {'gte': range_values[0], 'lte': range_values[1]}
    }
    return Range(**kwargs)


def create_number_range_filter(field, query_term):
    """Creates an ElasticSearch number range filter.
    Used for `elevation_min`/`elevation_max` for routes.
    """
    query_terms = query_term.split(',')
    range_values = list(map(parse_num, query_terms))
    range_values = [t for t in range_values if t is not None]

    n = len(range_values)
    if n != 2:
        return None

    kwargs_start = {field.field_min: {'gt': range_values[1]}}
    kwargs_end = {field.field_max: {'lt': range_values[0]}}
    return Bool(must_not=Bool(should=[
        Range(**kwargs_start),
        Range(**kwargs_end),
        Bool(must=[
            ~Exists(field=field.field_min),
            ~Exists(field=field.field_max)
        ])
    ]))


def create_bbox_filter(query_term):
    query_terms = query_term.split(',')
    bbox3857 = list(map(parse_num, query_terms))
    if len(bbox3857) != 4 or not all(bbox3857):
        return None

    # transform the bbox from 3857 to 4326
    xmin, ymin = transform(bbox3857[0], bbox3857[1])
    xmax, ymax = transform(bbox3857[2], bbox3857[3])

    if xmin == xmax or ymin == ymax:
        return None

    return GeoBoundingBox(
        geom={'left': xmin, 'bottom': ymin, 'right': xmax, 'top': ymax},
        type='indexed'
    )


# A function to transform from 3857 to 4326.
transform = partial(
        pyproj.transform,
        pyproj.Proj(init='epsg:3857'),
        pyproj.Proj(init='epsg:4326'))


def map_enum_to_int(enum_mapper, s):
    """
    Maps an enum value to an integer using an `enum_mapper` (one of the
    objects in `c2corg_common.sortable_search_attributes`.
    """
    if s in enum_mapper:
        return enum_mapper[s]
    else:
        return None


def parse_num(s):
    try:
        try:
            return int(s)
        except ValueError:
            val = float(s)
            if math.isnan(val):
                return None
            return val
    except ValueError:
        return None


def parse_float(s):
    try:
        return float(s)
    except ValueError:
        return None


def parse_enum_value(valid_values, s):
    if s in valid_values:
        return s
    else:
        return None


DATE_REGEX = re.compile('^(?:[0-9]{2})?[0-9]{2}-[0-3]?[0-9]-[0-3]?[0-9]$')


def parse_date(s):
    if DATE_REGEX.match(s):
        return s
    else:
        return None
