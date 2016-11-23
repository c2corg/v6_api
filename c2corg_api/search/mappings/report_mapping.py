from c2corg_api.models.report import REPORT_TYPE, Report
from c2corg_api.search.mapping import SearchDocument, BaseMeta
from c2corg_api.search.mapping_types import QueryableMixin, \
  QEnumArray, QInteger, QDate, QEnumRange

from c2corg_common.sortable_search_attributes import sortable_severities, \
  sortable_avalanche_levels, sortable_avalanche_slopes


class SearchReport(SearchDocument):
    class Meta(BaseMeta):
        doc_type = REPORT_TYPE

    activities = QEnumArray(
        'act', model_field=Report.activities)
    date = QDate('xdate', 'date')
    event_type = QEnumArray(
        'xtyp', model_field=Report.event_type)
    nb_participants = QInteger(
        'xpar', range=True)
    nb_impacted = QInteger(
        'ximp', range=True)
    severity = QEnumRange(
        'xsev', model_field=Report.severity,
        enum_mapper=sortable_severities)
    avalanche_level = QEnumRange(
        'xavlev', model_field=Report.avalanche_level,
        enum_mapper=sortable_avalanche_levels)
    avalanche_slope = QEnumRange(
        'xavslo', model_field=Report.avalanche_slope,
        enum_mapper=sortable_avalanche_slopes)
    elevation = QInteger(
        'xalt', range=True)

    FIELDS = [
      'activities', 'date', 'event_type', 'nb_participants',
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
            search_document, document, SearchReport.FIELDS)

        SearchDocument.copy_enum_range_fields(
            search_document, document, SearchReport.ENUM_RANGE_FIELDS,
            SearchReport)

        return search_document

SearchReport.queryable_fields = QueryableMixin.get_queryable_fields(
    SearchReport)
