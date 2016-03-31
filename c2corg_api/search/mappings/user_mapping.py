from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.search.mapping import SearchDocument, BaseMeta


class SearchUser(SearchDocument):
    class Meta(BaseMeta):
        doc_type = USERPROFILE_TYPE
