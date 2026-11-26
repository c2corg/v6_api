"""The actions on documents: merge, protect, revert, mask versions, delete."""
# The routes call the functions of views/ through web.handlers, with the
# checks their decorators declare (see web.documents.include_document_writes).

from typing import Annotated

from fastapi import Depends, Query, Request

from c2corg_api.views.document_delete import (
    delete_document,
    delete_document_locale,
    read_images_of_deletion,
    validate_document,
    validate_document_type,
    validate_requestor,
)
from c2corg_api.views.document_links import read_broken_links
from c2corg_api.views.document_merge import merge_documents
from c2corg_api.views.document_protect import protect_document, unprotect_document
from c2corg_api.views.document_revert import revert_document
from c2corg_api.views.document_trash import (
    read_deleted_document,
    read_deleted_documents,
    restore_deleted_document,
)
from c2corg_api.views.document_unmerge import read_merged_documents, unmerge_document
from c2corg_api.views.document_version_mask import mask_version, unmask_version
from c2corg_api.views.image_duplicates import (
    dismiss_duplicate_images,
    read_duplicate_images,
)
from c2corg_api.views.image_embeds import read_broken_embeds
from c2corg_api.views.image_orphans import read_orphan_images
from c2corg_api.web.auth import CurrentUser, current_user
from c2corg_api.web.checks import permission_check
from c2corg_api.web.documents import handler_arguments, include_handler_write
from c2corg_api.web.handlers import serve_read, typed_values
from c2corg_api.web.params import (
    DocType,
    Id,
    ImageType,
    Limit,
    Offset,
    day,
    natural,
)

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
    ('/documents/merged/{id:int}/unmerge', 'POST', unmerge_document),
    ('/images/duplicates/dismiss', 'POST', dismiss_duplicate_images),
]


def include(app):
    """Add the routes of this module to the FastAPI application."""
    for path, endpoint in (
        ('/documents/deleted', deleted_documents),
        ('/documents/deleted/{id:int}', deleted_document),
        ('/documents/merged', merged_documents),
        ('/images/orphans', orphan_images),
        ('/images/broken-embeds', broken_embeds),
        ('/documents/broken-links', broken_links),
        ('/images/duplicates', duplicate_images),
        ('/documents/delete/{id:int}/images', images_of_deletion),
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


def merged_documents(
    request: Request,
    user: User,
    _: Moderator,
    offset: Annotated[
        Offset | None, Query(description='The first merge, from 0.')
    ] = None,
    limit: Annotated[Limit | None, Query(description='How many merges.')] = None,
):
    """Return the merges a moderator can undo, the last first."""
    validated = {'offset': offset, 'limit': limit}
    return serve_read(request, user, [typed_values(validated)], read_merged_documents)


def deleted_document(request: Request, user: User, _: Moderator, id: Id):
    """Return a deleted document: its locales and the rows kept."""
    validated = {'id': id}
    return serve_read(request, user, [typed_values(validated)], read_deleted_document)


def orphan_images(
    request: Request,
    user: User,
    _: Moderator,
    offset: Annotated[
        Offset | None, Query(description='The first image, from 0.')
    ] = None,
    limit: Annotated[
        Limit | None, Query(description='How many: 30 by default, 100 at most.')
    ] = None,
    image_type: Annotated[
        ImageType | None, Query(description='Only the images of this type.')
    ] = None,
):
    """Return the images linked to no document, the last created first."""
    validated = {'offset': offset, 'limit': limit, 'image_type': image_type}
    return serve_read(request, user, [typed_values(validated)], read_orphan_images)


def broken_embeds(
    request: Request,
    user: User,
    _: Moderator,
    offset: Annotated[
        Offset | None, Query(description='The first embed, from 0.')
    ] = None,
    limit: Annotated[
        Limit | None, Query(description='How many: 30 by default, 100 at most.')
    ] = None,
):
    """Return the images shown in texts ([img=ID]) that do not show."""
    validated = {'offset': offset, 'limit': limit}
    return serve_read(request, user, [typed_values(validated)], read_broken_embeds)


def broken_links(
    request: Request,
    user: User,
    _: Moderator,
    offset: Annotated[
        Offset | None, Query(description='The first link, from 0.')
    ] = None,
    limit: Annotated[
        Limit | None, Query(description='How many: 30 by default, 100 at most.')
    ] = None,
):
    """Return the broken links in the texts of the collaborative documents."""
    validated = {'offset': offset, 'limit': limit}
    return serve_read(request, user, [typed_values(validated)], read_broken_links)


def duplicate_images(
    request: Request,
    user: User,
    _: Moderator,
    offset: Annotated[
        Offset | None, Query(description='The first set, from 0.')
    ] = None,
    limit: Annotated[
        Limit | None, Query(description='How many sets: 30 by default, 100 at most.')
    ] = None,
    same_document: Annotated[
        bool | None,
        Query(description='Only the sets with two images linked to one document.'),
    ] = None,
):
    """Return the sets of duplicate images, the last uploaded first."""
    validated = {'offset': offset, 'limit': limit, 'same_document': same_document}
    return serve_read(request, user, [typed_values(validated)], read_duplicate_images)


def images_of_deletion(request: Request, user: User, id: Id):
    """Return how many images a deletion takes along, and leaves orphan."""
    # the checks of the deletion: who may delete this document, and whether
    # its links allow it (a main waypoint, the only route of an outing...)
    validated = {'id': id}
    return serve_read(
        request,
        user,
        [
            typed_values(validated),
            validate_document_type,
            validate_document,
            validate_requestor,
        ],
        read_images_of_deletion,
        permission='authenticated',
    )


images_of_deletion.permission = 'authenticated'
images_of_deletion.described = True

# read by the route inventory of the contract tests (routes.txt)
for _endpoint in (
    deleted_documents,
    deleted_document,
    merged_documents,
    orphan_images,
    broken_embeds,
    broken_links,
    duplicate_images,
):
    _endpoint.permission = 'moderator'
    # described in the OpenAPI document (see web.openapi)
    _endpoint.described = True
