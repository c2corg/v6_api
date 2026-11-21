"""The actions of the users: associations, follows, blocks, preferences, tags."""
# The routes call the functions of views/ through web.handlers, with the
# checks their decorators declare (see web.documents.include_document_writes).

from c2corg_api.views.association import add_association, remove_association
from c2corg_api.views.favourite import add_favourite, remove_favourite
from c2corg_api.views.user_block import block_user, unblock_user
from c2corg_api.views.user_follow import follow_user, unfollow_user
from c2corg_api.views.user_mailinglists import update_mailinglists
from c2corg_api.views.user_preferences import update_preferences
from c2corg_api.views.user_removal import (
    cancel_removal_request,
    create_removal_request,
    unvalidate_removal_request,
    update_removal_request,
    validate_removal_request,
)
from c2corg_api.web.documents import handler_arguments, include_handler_write

# (path, HTTP method, function)
WRITES = [
    ('/associations', 'POST', add_association),
    ('/associations', 'DELETE', remove_association),
    ('/users/follow', 'POST', follow_user),
    ('/users/unfollow', 'POST', unfollow_user),
    ('/users/block', 'POST', block_user),
    ('/users/unblock', 'POST', unblock_user),
    ('/users/removals', 'POST', create_removal_request),
    ('/users/removals/{id:int}', 'PUT', update_removal_request),
    ('/users/removals/{id:int}/validate', 'POST', validate_removal_request),
    ('/users/removals/{id:int}/unvalidate', 'POST', unvalidate_removal_request),
    ('/users/removals/{id:int}/cancel', 'POST', cancel_removal_request),
    ('/users/preferences', 'POST', update_preferences),
    ('/users/mailinglists', 'POST', update_mailinglists),
]


# the former routes of the favourites, for the clients not updated yet (see
# web.favourites): (path, function, operation id)
TAG_WRITES = [
    ('/tags/add', add_favourite, 'tag_document'),
    ('/tags/remove', remove_favourite, 'untag_document'),
]


def include(app):
    """Add the routes of this module to the FastAPI application."""
    for path, http_method, function in WRITES:
        include_handler_write(
            app, path, http_method, function, *handler_arguments(function)
        )
    for path, function, operation_id in TAG_WRITES:
        include_handler_write(
            app,
            path,
            'POST',
            function,
            *handler_arguments(function),
            operation_id=operation_id,
        )
