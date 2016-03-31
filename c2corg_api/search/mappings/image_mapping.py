from c2corg_api.models.image import IMAGE_TYPE
from c2corg_api.search.mapping import SearchDocument, BaseMeta


class SearchImage(SearchDocument):
    class Meta(BaseMeta):
        doc_type = IMAGE_TYPE
