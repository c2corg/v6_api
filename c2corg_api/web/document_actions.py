"""The actions on documents: merge, protect, revert, mask versions, delete."""
# The routes call the functions of views/ through web.handlers, with the
# checks their decorators declare (see web.documents.include_document_writes).

from typing import Annotated

from fastapi import Depends, Query, Request

from c2corg_api.views.document_delete import delete_document, delete_document_locale
from c2corg_api.views.document_merge import merge_documents
from c2corg_api.views.document_protect import protect_document, unprotect_document
from c2corg_api.views.document_revert import revert_document
from c2corg_api.views.document_trash import (
    read_deleted_document,
    read_deleted_documents,
    restore_deleted_document,
)
from c2corg_api.views.document_version_mask import mask_version, unmask_version
from c2corg_api.web.auth import CurrentUser, current_user
from c2corg_api.web.checks import permission_check
from c2corg_api.web.documents import handler_arguments, include_handler_write
from c2corg_api.web.handlers import serve_read, typed_values
from c2corg_api.web.params import DocType, Id, Limit, Offset, day, natural

User = Annotated[CurrentUser | None, Depends(current_user)]
Moderator = Annotated[None, Depends(permission_check('moderator'))]

# (path, HTTP method, function); a numeric id only, as the document routes
WRITES = [
    ('/documents/merge', 'POST', merge_documents),
    ('/documents/protect', 'POST', protect_document),
    ('/documents/unprotect', 'POST', unprotect_document),
    ('/documents/revert', 'POST', revert_document),
    ('/versions/mask', 'POST', mask_version),
    ('/versions/unmask', 'POST', unmask_version),
    ('/documents/delete/{id:int}', 'DELETE', delete_document),
    ('/documents/delete/{id:int}/{lang}', 'DELETE', delete_document_locale),
    ('/documents/deleted/{id:int}/restore', 'POST', restore_deleted_document),
]


def include(app):
    """Add the routes of this module to the FastAPI application."""
    for path, endpoint in (
        ('/documents/deleted', deleted_documents),
        ('/documents/deleted/{id:int}', deleted_document),
    ):
        app.add_api_route(
            path,
            endpoint,
            methods=['GET', 'HEAD'],
            operation_id=endpoint.__name__,
            tags=['documents'],
        )
    for path, http_method, function in WRITES:
        include_handler_write(
            app, path, http_method, function, *handler_arguments(function)
        )


def deleted_documents(
    request: Request,
    user: User,
    _: Moderator,
    offset: Annotated[
        Offset | None, Query(description='The first deleted document, from 0.')
    ] = None,
    limit: Annotated[
        Limit | None, Query(description='How many: 30 by default, 100 at most.')
    ] = None,
    type: Annotated[
        DocType | None, Query(description='Only the documents of this type.')
    ] = None,
    author: Annotated[
        natural('author') | None,
        Query(description='Only the documents written by this user.'),
    ] = None,
    deleted_by: Annotated[
        natural('deleted_by') | None,
        Query(description='Only the documents deleted by this user.'),
    ] = None,
    deleted_since: Annotated[
        day('deleted_since') | None,
        Query(description='Only the documents deleted this day or after.'),
    ] = None,
    deleted_until: Annotated[
        day('deleted_until') | None,
        Query(description='Only the documents deleted this day or before.'),
    ] = None,
):
    """Return the deleted documents a moderator can restore, the last first."""
    validated = {
        'offset': offset,
        'limit': limit,
        'type': type,
        'author': author,
        'deleted_by': deleted_by,
        'deleted_since': deleted_since,
        'deleted_until': deleted_until,
    }
    return serve_read(request, user, [typed_values(validated)], read_deleted_documents)


def deleted_document(request: Request, user: User, _: Moderator, id: Id):
    """Return a deleted document: its locales and the rows kept."""
    validated = {'id': id}
    return serve_read(request, user, [typed_values(validated)], read_deleted_document)


# read by the route inventory of the contract tests (routes.txt)
for _endpoint in (deleted_documents, deleted_document):
    _endpoint.permission = 'moderator'
    # described in the OpenAPI document (see web.openapi)
    _endpoint.described = True
