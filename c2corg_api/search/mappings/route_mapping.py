from c2corg_api.models.route import ROUTE_TYPE
from c2corg_api.search.mapping import SearchDocument, BaseMeta


class SearchRoute(SearchDocument):
    class Meta(BaseMeta):
        doc_type = ROUTE_TYPE
