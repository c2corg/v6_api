from elasticsearch_dsl import String, Long, Integer, Boolean

# this module contains classes to mark the fields of a mapping that can be
# used in a search.

meta_param_keys = ('pl', 'limit', 'offset')

# parameters used for the search service that can not be used as query fields
reserved_query_fields = meta_param_keys + ('q', 'bbox')


class QueryableMixin(object):
    def __init__(self, query_name, *args, **kwargs):
        self._query_name = query_name
        if 'enum' in kwargs:
            self._enum = kwargs['enum']
            del kwargs['enum']
        if 'model_field' in kwargs:
            model_field = kwargs['model_field']
            del kwargs['model_field']
            model_type = model_field.property.columns[0].type
            if hasattr(model_type, 'enums'):
                # column with enum
                self._enum = model_type.enums
            elif hasattr(model_type, 'item_type') and \
                    hasattr(model_type.item_type, 'enums'):
                # column with array of enum
                self._enum = model_type.item_type.enums
        if 'range' in kwargs:
            self._range = kwargs['range']
            del kwargs['range']
        if 'date_range' in kwargs:
            self._date_range = kwargs['date_range']
            del kwargs['date_range']
        if 'enum_range' in kwargs:
            self._enum_range = kwargs['enum_range']
            del kwargs['enum_range']
        if 'is_bool' in kwargs:
            self._is_bool = kwargs['is_bool']
            del kwargs['is_bool']
        if 'is_id' in kwargs:
            self._is_id = kwargs['is_id']
            del kwargs['is_id']
        super(QueryableMixin, self).__init__(*args, **kwargs)

    @staticmethod
    def get_queryable_fields(search_model):
        queryable_fields = {}
        fields = search_model._doc_type.mapping
        for field_name in fields:
            field = fields[field_name]
            if isinstance(field, QueryableMixin):
                field._name = field_name
                if field._query_name in queryable_fields or \
                        field._query_name in reserved_query_fields:
                    raise ReferenceError(
                        'Query field name `{}` is already used for {}'.format(
                            field._query_name, search_model))
                queryable_fields[field._query_name] = field
        return queryable_fields


def get_as_queryable(clazz):
    class QClass(QueryableMixin, clazz):
        pass
    return QClass


class Enum(String):
    """Field type for enums that should not be analyzed before indexing.
    """
    def __init__(self, *args, **kwargs):
        kwargs['index'] = 'not_analyzed'
        super(Enum, self).__init__(*args, **kwargs)


class EnumArray(Enum):
    """Arrays are handled in an implicit manner in ElasticSearch. This type is
    only to mark that a field may contain multiple values.
    """
    pass


# queryable types
QEnum = get_as_queryable(Enum)
QEnumArray = get_as_queryable(EnumArray)
QLong = get_as_queryable(Long)
QInteger = get_as_queryable(Integer)
QBoolean = get_as_queryable(Boolean)


class QDateRange(QueryableMixin):
    """Search field for date-ranges. Used for date_start/date_end for
    outings.
    """
    def __init__(self, query_name, field_date_start, field_date_end,
                 *args, **kwargs):
        self.field_date_start = field_date_start
        self.field_date_end = field_date_end
        kwargs['date_range'] = True
        super(QDateRange, self).__init__(query_name, *args, **kwargs)


class QEnumRange(QueryableMixin, Integer):
    """Search field for enum ranges. To make it more convenient to search
    for ranges with enum fields (e.g. to search a route with a rating between
    'AD' and 'ED') the enum values are converted to integer values and
    stored as such in ElasticSearch. When doing a search, a filter using these
    numbers is used.
    The enums are converted to integers using the mappers defined in
    `c2corg_common.sortable_search_attributes`.
    """
    def __init__(self, query_name, model_field, enum_mapper,
                 *args, **kwargs):
        self._enum_mapper = enum_mapper
        kwargs['model_field'] = model_field
        kwargs['enum_range'] = True
        super(QEnumRange, self).__init__(query_name, *args, **kwargs)
