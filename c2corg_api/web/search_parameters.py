"""The search filters of the document listings, as OpenAPI parameters."""
# Built from the queryable fields of the search mappings (search/mappings/),
# which search.search_filters reads to build the Elasticsearch filters: the
# description stays in step with the filters. The view still reads them;
# a value it cannot parse is ignored, not refused.


def _list(items):
    # a list of values, comma separated (`a,b`)
    return {'type': 'array', 'items': items}, {'style': 'form', 'explode': False}


_RANGE = '`min,max`, where one side may be empty (`1500,` for 1500 or more).'
_OVERLAP = '`min,max`: the documents whose own range overlaps it.'
_DATES = 'Dates `YYYY-MM-DD`: one date, or `start,end`, the documents in that range.'


def _kind(field):
    """Return the description, schema and style of a filter."""
    # in the order of search_filters.create_filter
    text = {'type': 'string'}
    if getattr(field, '_range', False):
        return f'Numbers: {_RANGE}', text, {}
    if getattr(field, '_enum_range', False):
        return f'{_RANGE} {_ordered(field)}', text, {}
    if getattr(field, '_enum_range_min_max', False):
        return f'{_OVERLAP} {_ordered(field)}', text, {}
    if hasattr(field, '_enum'):
        schema, style = _list({'type': 'string', 'enum': list(field._enum)})
        return 'One or more values, comma separated.', schema, style
    if getattr(field, '_is_bool', False):
        return '`true` or `false` (also `1` or `0`).', {'type': 'boolean'}, {}
    if getattr(field, '_is_id', False):
        schema, style = _list({'type': 'integer'})
        return 'One or more document ids, comma separated.', schema, style
    if getattr(field, '_date_range', False) or getattr(field, '_date', False):
        return _DATES, text, {}
    if getattr(field, '_period', False):
        return (
            'Dates `YYYY-MM-DD,YYYY-MM-DD`: the documents in that period of the '
            'year, whatever the year.',
            text,
            {},
        )
    if getattr(field, '_integer_range', False):
        return f'Numbers: {_OVERLAP}', text, {}
    return None


def _ordered(field):
    values = ', '.join(f'`{value}`' for value in field._enum_mapper)
    return f'The values, in their order: {values}.'


def _fields(field):
    """Return the fields a filter is on, for its description."""
    # a range of two fields (date_start/date_end, elevation_min/max) has no
    # field of its own
    names = [
        getattr(field, attribute, None)
        for attribute in (
            'field_date_start',
            'field_date_end',
            'field_min',
            'field_max',
        )
    ]
    names = [name for name in names if name] or [getattr(field, '_name', None)]
    return ' and '.join(f'`{name}`' for name in names if name) or 'a field'


def search_filter_parameters(doc_type):
    """Return the OpenAPI parameters of the search filters of a document type."""
    from c2corg_api.search import search_documents

    search_model = search_documents.get(doc_type)
    if search_model is None:
        return []
    parameters = []
    for name, field in sorted(search_model.queryable_fields.items()):
        kind = _kind(field)
        if kind is None:
            # a field create_filter does not filter on
            continue
        description, schema, style = kind
        parameters.append(
            {
                'name': name,
                'in': 'query',
                'required': False,
                'description': f'Filter on {_fields(field)}. {description}',
                'schema': schema,
                **style,
            }
        )
    return parameters
