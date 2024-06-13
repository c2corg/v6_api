import pprint

from elasticsearch_dsl import Text, Long, Integer, Boolean, Date

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
        if 'period' in kwargs:
            self._period = kwargs['period']
            del kwargs['period']
        if 'date' in kwargs:
            self._date = kwargs['date']
            del kwargs['date']
        if 'integer_range' in kwargs:
            self._integer_range = kwargs['integer_range']
            del kwargs['integer_range']
        if 'enum_range' in kwargs:
            self._enum_range = kwargs['enum_range']
            del kwargs['enum_range']
        if 'enum_range_min_max' in kwargs:
            self._enum_range_min_max = kwargs['enum_range_min_max']
            del kwargs['enum_range_min_max']
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
        pprint.pprint(search_model)
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


class Enum(Text):
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
    """Search field for date-ranges with two fields (start/end). Used for
    `date_start`/`date_end` for outings.
    """
    def __init__(self, query_name, field_date_start, field_date_end,
                 *args, **kwargs):
        self.field_date_start = field_date_start
        self.field_date_end = field_date_end
        kwargs['date_range'] = True
        super(QDateRange, self).__init__(query_name, *args, **kwargs)


class QPeriod(QueryableMixin):
    """Search field for period with two fields (start/end). Used for
    `date_start`/`date_end` for outings, regardless of the year.
    """
    def __init__(self, query_name, field_date_start, field_date_end,
                 *args, **kwargs):
        self.field_date_start = field_date_start
        self.field_date_end = field_date_end
        kwargs['period'] = True
        super(QPeriod, self).__init__(query_name, *args, **kwargs)


class QDate(QueryableMixin, Date):
    """Search field for date-ranges with a single field. Used for `date` for
    images.
    """
    def __init__(self, query_name, field_date, *args, **kwargs):
        self._field_date = field_date
        kwargs['date'] = True
        super(QDate, self).__init__(query_name, *args, **kwargs)


class QNumberRange(QueryableMixin):
    """Search field for number ranges. Used for elevation_min/elevation_max
    for routes.
    """
    def __init__(self, query_name, field_min, field_max, *args, **kwargs):
        self.field_min = field_min
        self.field_max = field_max
        kwargs['integer_range'] = True
        super(QNumberRange, self).__init__(query_name, *args, **kwargs)


class QEnumRange(QueryableMixin, Integer):
    """Search field for enum ranges. To make it more convenient to search
    for ranges with enum fields (e.g. to search a route with a rating between
    'AD' and 'ED') the enum values are converted to integer values and
    stored as such in ElasticSearch. When doing a search, a filter using these
    numbers is used.
    The enums are converted to integers using the mappers defined in
    `c2corg_api.models.common.sortable_search_attributes`.
    """
    def __init__(self, query_name, model_field, enum_mapper,
                 *args, **kwargs):
        self._enum_mapper = enum_mapper
        kwargs['model_field'] = model_field
        kwargs['enum_range'] = True
        super(QEnumRange, self).__init__(query_name, *args, **kwargs)


class QEnumRangeMinMax(QueryableMixin):
    """Search field for combined enums. For example the fields
    `climbing_rating_min` and `climbing_rating_max` are combined into a single
    search field.
    """
    def __init__(self, query_name, field_min, field_max, enum_mapper,
                 *args, **kwargs):
        self.field_min = field_min
        self.field_max = field_max
        self._enum_mapper = enum_mapper
        kwargs['enum_range_min_max'] = True
        super(QEnumRangeMinMax, self).__init__(query_name, *args, **kwargs)
