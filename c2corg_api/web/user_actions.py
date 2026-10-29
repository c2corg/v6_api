"""The writes of the users on documents and users: associations, tags, follows..."""
# The routes call the view classes of views/ through web.compat, with the
# checks their Cornice decorators declare (see web.documents.include_write).

from c2corg_api.views.association import AssociationRest
from c2corg_api.views.document_tag import DocumentTagRest, DocumentUntagRest
from c2corg_api.views.user_block import UserBlockRest, UserUnblockRest
from c2corg_api.views.user_follow import UserFollowRest, UserUnfollowRest
from c2corg_api.views.user_mailinglists import UserMailinglistsRest
from c2corg_api.views.user_preferences import UserFilterPreferencesRest
from c2corg_api.web.documents import include_write

# (path, HTTP method, view class, method of the view class)
WRITES = [
    ('/associations', 'POST', AssociationRest, 'collection_post'),
    ('/associations', 'DELETE', AssociationRest, 'collection_delete'),
    ('/tags/add', 'POST', DocumentTagRest, 'post'),
    ('/tags/remove', 'POST', DocumentUntagRest, 'post'),
    ('/users/follow', 'POST', UserFollowRest, 'post'),
    ('/users/unfollow', 'POST', UserUnfollowRest, 'post'),
    ('/users/block', 'POST', UserBlockRest, 'post'),
    ('/users/unblock', 'POST', UserUnblockRest, 'post'),
    ('/users/preferences', 'POST', UserFilterPreferencesRest, 'post'),
    ('/users/mailinglists', 'POST', UserMailinglistsRest, 'post'),
]


def include(app):
    """Add the routes of this module to the FastAPI application."""
    for path, http_method, view_class, method in WRITES:
        include_write(app, path, http_method, view_class, method)
