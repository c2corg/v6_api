from c2corg_api.models.xreport import XREPORT_TYPE, Xreport
from c2corg_api.search.mapping import SearchDocument, BaseMeta
from c2corg_api.search.mapping_types import QueryableMixin, \
    QEnumArray, QInteger, QDate, QEnumRange

from c2corg_api.models.common.sortable_search_attributes import \
    sortable_severities, sortable_avalanche_levels, sortable_avalanche_slopes


class SearchXreport(SearchDocument):
#    class Meta(BaseMeta):
#        doc_type = XREPORT_TYPE

    event_activity = QEnumArray(
        'act', model_field=Xreport.event_activity)
    date = QDate('xdate', 'date')
    event_type = QEnumArray(
        'xtyp', model_field=Xreport.event_type)
    nb_participants = QInteger(
        'xpar', range=True)
    nb_impacted = QInteger(
        'ximp', range=True)
    severity = QEnumRange(
        'xsev', model_field=Xreport.severity,
        enum_mapper=sortable_severities)
    avalanche_level = QEnumRange(
        'xavlev', model_field=Xreport.avalanche_level,
        enum_mapper=sortable_avalanche_levels)
    avalanche_slope = QEnumRange(
        'xavslo', model_field=Xreport.avalanche_slope,
        enum_mapper=sortable_avalanche_slopes)
    elevation = QInteger(
        'xalt', range=True)

    FIELDS = [
        'date', 'event_activity', 'event_type', 'nb_participants',
        'nb_impacted', 'elevation'
    ]

    ENUM_RANGE_FIELDS = [
        'severity', 'avalanche_level', 'avalanche_slope'
    ]

    @staticmethod
    def to_search_document(document, index):
        search_document = SearchDocument.to_search_document(document, index)

        if document.redirects_to:
            return search_document

        SearchDocument.copy_fields(
            search_document, document, SearchXreport.FIELDS)

        SearchDocument.copy_enum_range_fields(
            search_document, document, SearchXreport.ENUM_RANGE_FIELDS,
            SearchXreport)

        return search_document


SearchXreport.queryable_fields = QueryableMixin.get_queryable_fields(
    SearchXreport)
SearchXreport.queryable_fields['date'] = QDate('xdate', 'date')
