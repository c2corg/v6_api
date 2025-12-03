import logging
from operator import and_, or_
import re
from shapely.geometry import Polygon
from geoalchemy2.shape import from_shape
from sqlalchemy import nullslast
from geoalchemy2.functions import ST_Intersects, ST_Transform
from c2corg_api.models.utils import ArrayOfEnum

log = logging.getLogger(__name__)

BBCODE_TAGS = [
    'b', 'i', 'u', 's', 'q', 'c', 'sup', 'ind', 'url', 'email', 'acr(onym)?',
    'colou?r', 'picto', 'p', 'center', 'right', 'left', 'justify',
    'abs(tract)?', 'imp(ortant)?', 'warn(ing)?', 'col', 'img', 'quote'
]
BBCODE_REGEX = \
    [r'\[{0}\]'.format(tag) for tag in BBCODE_TAGS] + \
    [r'\[\/{0}\]'.format(tag) for tag in BBCODE_TAGS] + [
        r'\[url([^\[\]]*?)\]',
        r'\[email([^\[\]]*?)\]',
        r'\[acr(onym)?([^\[\]]*?)\]',
        r'\[colou?r([^\[\]]*?)\]',
        r'\[picto([^\[\]]*?)\]',
        r'\[col([^\[\]]*?)\]',
        r'\[toc([^\[\]]*?)\]',
        r'\[img([^\[\]]*?)\]',
    ]
BBCODE_REGEX_ALL = re.compile('|'.join(BBCODE_REGEX))


def strip_bbcodes(s):
    """Remove all bbcodes from the given text.
    """
    if not s:
        return s
    else:
        return BBCODE_REGEX_ALL.sub(' ', s)


def get_title(title, title_prefix):
    return title_prefix + ' : ' + title if title_prefix else title


def build_sqlalchemy_filters(
    search_dict, # elastic search dict
    document_model, # the model (waypoint, routes, etc...)
    filter_map, # for multicriteria search (ex : searching a waypoint by area id)
    geometry_model, # the Geometry model (where ce access to geometry), most likely always DocumentGeometry
    range_enum_map, # the mapper for range enum, most likely always sortable_search_attr_by_field
    title_columns=None # the column for the title (ex:  Waypoint -> title, Route -> title and title_prefix)
):
    """
    Build SQLAlchemy filter for documents (Waypoint, Route, etc.) based on filters that would normally be used by ElasticSearch
    
    this can then be used to filter directly in a DB query
    
    Usage Example : 
    
    search = build_query(params, meta_params, WAYPOINT_TYPE)

    search_dict = search.to_dict()
    
    filter_conditions, sort_expressions, needs_locale_join, langs = build_sqlalchemy_filters(
        search_dict=search_dict,
        document_model=Waypoint,
        filter_map={"areas": Area,},
        geometry_model=DocumentGeometry,
        range_enum_map=sortable_search_attr_by_field,
        title_columns=[DocumentLocale.title]
    )
    
    query = DBSession.query(Waypoint).filter(filter_conditions).order_by(*sort_expressions)
    
    """

    filters = search_dict.get("query", {}).get("bool", {}).get("filter", [])
    must_list = search_dict.get("query", {}).get("bool", {}).get("must", [])

    filter_conditions = []
    needs_locale_join = False
    langs = []

    # corresponds to the elastic search ?q= which looks for title
    # use title_columns to specify in which columns to look for
    query_value = None
    for item in must_list:
        mm = item.get("multi_match")
        if mm:
            query_value = mm.get("query")
            break

    if query_value and title_columns:
        needs_locale_join = True
        like_clauses = [col.ilike(f"%{query_value}%") for col in title_columns]
        filter_conditions.append(or_(*like_clauses))

    # loop over all elastic search filters
    for f in filters:
        for filter_key, param in f.items():

            for param_key, param_value in param.items():

                # available_locales to get langs
                if param_key == "available_locales":
                    langs = param_value if isinstance(
                        param_value, list) else [param_value]

                # geometry-based filtering -> bbox
                elif param_key == "geom":
                    col = getattr(geometry_model, "geom")
                    polygon = Polygon([
                        (param_value["left"], param_value["bottom"]),
                        (param_value["right"], param_value["bottom"]),
                        (param_value["right"], param_value["top"]),
                        (param_value["left"], param_value["top"]),
                        (param_value["left"], param_value["bottom"]),
                    ])
                    polygon_wkb = from_shape(polygon, srid=4326)
                    filter_conditions.append(ST_Intersects(
                        ST_Transform(col, 4326), polygon_wkb))

                # special cases of documents associated to other doc
                elif param_key in filter_map:
                    col = getattr(filter_map[param_key], "document_id")
                    if isinstance(param_value, list):
                        checks = [col == v for v in param_value]
                        if checks:
                            or_expr = checks[0]
                            for check in checks[1:]:
                                or_expr = or_expr | check
                        filter_conditions.append(or_expr)
                    else:
                        filter_conditions.append(col == param_value)

                # generic attribute filters on the document model
                else:
                    col = getattr(document_model, param_key)
                    column = col.property.columns[0]
                    col_type = column.type

                    # for range attributes
                    if filter_key == "range":
                        filter_conditions.append(
                            build_range_expression(
                                col, param_value, range_enum_map.get(param_key))
                        )

                    # for terms
                    elif filter_key == "terms":
                        values = param_value if isinstance(
                            param_value, (list, tuple)) else [param_value]
                        filter_conditions.append(
                            build_terms_expression(col, values, col_type)
                        )

                    # for term
                    elif filter_key == "term":
                        filter_conditions.append(
                            build_term_expression(col, param_value, col_type)
                        )

                    else:
                        continue

    # combine and conditions
    final_filter = combine_conditions(filter_conditions)

    # build sort expressions
    sort_expressions = build_sort_expressions(
        search_dict.get("sort", []), document_model
    )

    # return each valuable variable to be used later in a sql alchemy DBSession.query
    return final_filter, sort_expressions, needs_locale_join, langs


def build_range_expression(col, param_value, enum_map):
    """
    build sql alchemy filter for range expressions
    """
    gte = param_value.get("gte")
    lte = param_value.get("lte")

    # ENUM RANGE (enum_map: value -> number)
    if enum_map:
        values = []
        if gte is not None and lte is not None:
            if gte == lte:
                values = [val for val, num in enum_map.items() if num == gte]
            else:
                values = [val for val, num in enum_map.items() if num >= gte and num < lte]
        elif gte is not None:
            values = [val for val, num in enum_map.items() if num >= gte]
        elif lte is not None:
            values = [val for val, num in enum_map.items() if num < lte]

        checks = [col == v for v in values]
        if not checks:
            return False
        or_expr = checks[0]
        for check in checks[1:]:
            or_expr = or_expr | check
        return or_expr

    # NUMERIC RANGE
    clauses = []
    if gte is not None:
        clauses.append(col >= gte)
    if lte is not None:
        clauses.append(col <= lte)
    if not clauses:
        return False
    return and_(*clauses)

def build_terms_expression(col, values, col_type):
    """
    build sql alchemy filter for terms expressions
    """
    # normalize values to list/tuple
    values = values if isinstance(values, (list, tuple)) else [values]
    if not values:
        return True

    if isinstance(col_type, ArrayOfEnum):
        checks = [col.any(v) for v in values]
        if not checks:
            return True
        # build OR by folding with |
        or_expr = checks[0]
        for check in checks[1:]:
            or_expr = or_expr | check
        return or_expr

    # non-array enum
    if len(values) == 1:
        return col == values[0]
    return col.in_(values)

def build_term_expression(col, value, col_type):
    """
    build sql alchemy filter for term expressions
    """
    if isinstance(col_type, ArrayOfEnum):
        return col.any(value)
    return col == value


def combine_conditions(conditions):
    """
    useful functions to combine conditions to later apply them in a .filter
    """
    if not conditions:
        return True
    if len(conditions) == 1:
        return conditions[0]
    expr = conditions[0]
    for c in conditions[1:]:
        expr = expr & c
    return expr


def build_sort_expressions(sort_config, document_model):
    """
    build sql alchemy sort expressions
    """
    sort_expressions = []

    for sort in sort_config:
        if sort == "undefined":
            continue

        # DESC
        if hasattr(sort, "items"):
            for attr, order in sort.items():
                col = (
                    getattr(document_model, "document_id")
                    if attr == "id" else getattr(document_model, attr)
                )
                sort_expressions.append(
                    nullslast(col.desc() if order == "desc" else col.asc())
                )

        # ASC
        else:
            col = getattr(document_model, sort)
            sort_expressions.append(nullslast(col.asc()))

    return sort_expressions
