"""The actions of the users: associations, tags, follows, blocks, preferences."""
# The routes call the functions of views/ through web.handlers, with the
# checks their decorators declare (see web.documents.include_document_writes).

from c2corg_api.views.association import add_association, remove_association
from c2corg_api.views.document_tag import tag_document, untag_document
from c2corg_api.views.user_block import block_user, unblock_user
from c2corg_api.views.user_follow import follow_user, unfollow_user
from c2corg_api.views.user_mailinglists import update_mailinglists
from c2corg_api.views.user_preferences import update_preferences
from c2corg_api.web.documents import handler_arguments, include_handler_write

# (path, HTTP method, function)
WRITES = [
    ('/associations', 'POST', add_association),
    ('/associations', 'DELETE', remove_association),
    ('/tags/add', 'POST', tag_document),
    ('/tags/remove', 'POST', untag_document),
    ('/users/follow', 'POST', follow_user),
    ('/users/unfollow', 'POST', unfollow_user),
    ('/users/block', 'POST', block_user),
    ('/users/unblock', 'POST', unblock_user),
    ('/users/preferences', 'POST', update_preferences),
    ('/users/mailinglists', 'POST', update_mailinglists),
]


def include(app):
    """Add the routes of this module to the FastAPI application."""
    for path, http_method, function in WRITES:
        include_handler_write(
            app, path, http_method, function, *handler_arguments(function)
        )
