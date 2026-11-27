"""The routes of the favourites of the users and of their folders."""
# The routes call the functions of views/favourite.py through web.handlers,
# as the other routes of the users do; /tags/... are their former routes
# (web.misc, web.user_actions).

from typing import Annotated

from fastapi import Depends, Path, Query, Request

from c2corg_api.views.favourite import (
    add_favourite,
    create_folder,
    delete_folder,
    move_favourite,
    order_folders,
    read_favourite,
    read_favourites,
    read_folders,
    remove_favourite,
    rename_folder,
)
from c2corg_api.web.auth import CurrentUser, current_user
from c2corg_api.web.checks import permission_check
from c2corg_api.web.documents import handler_arguments, include_handler_write
from c2corg_api.web.handlers import serve_read, typed_values
from c2corg_api.web.params import Lang, natural

User = Annotated[CurrentUser | None, Depends(current_user)]

JSON = ['application/json']

# the writes: (path, HTTP method, function), with the checks of the
# function's decorator (see web.documents.include_document_writes)
WRITES = [
    ('/favourites/add', 'POST', add_favourite),
    ('/favourites/remove', 'POST', remove_favourite),
    ('/favourites/move', 'POST', move_favourite),
    ('/favourites/folders', 'POST', create_folder),
    ('/favourites/folders/order', 'POST', order_folders),
    ('/favourites/folders/{id:int}', 'PUT', rename_folder),
    ('/favourites/folders/{id:int}', 'DELETE', delete_folder),
]


def include(app):
    """Add the routes of this module to the FastAPI application."""
    methods = ['GET', 'HEAD']
    # a numeric id only, as the document routes (see web.documents)
    for path, endpoint in (
        ('/favourites', favourites),
        ('/favourites/folders', folders),
        ('/favourites/has/{document_id:int}', has_favourite),
    ):
        app.add_api_route(
            path,
            endpoint,
            methods=methods,
            operation_id=endpoint.__name__,
            tags=['favourites'],
        )
    for path, http_method, function in WRITES:
        include_handler_write(
            app, path, http_method, function, *handler_arguments(function)
        )


def _checks():
    # the content type and the permission are checked before the parameters,
    # as Cornice and Pyramid did
    check = permission_check('authenticated', JSON)
    return Annotated[None, Depends(check)]


def favourites(
    request: Request,
    user: User,
    _: _checks(),
    lang: Annotated[
        Lang | None,
        Query(
            alias='pl',
            description='The title of each document in this language if it '
            'exists, else in the best other one; the language of the user '
            'by default.',
        ),
    ] = None,
):
    """Return the favourites and the favourite folders of the authenticated user."""
    validated = {'lang': lang}
    return serve_read(request, user, [typed_values(validated)], read_favourites)


def folders(request: Request, user: User, _: _checks()):
    """Return the favourite folders of the authenticated user, in their order."""
    return serve_read(request, user, [], read_folders)


def has_favourite(
    request: Request,
    user: User,
    _: _checks(),
    document_id: Annotated[
        natural('document_id'), Path(description='The document id.')
    ],
):
    """Tell whether the authenticated user has a document in favourites."""
    validated = {'document_id': document_id}
    return serve_read(request, user, [typed_values(validated)], read_favourite)


for endpoint in (favourites, folders, has_favourite):
    # read by the route inventory of the contract tests (routes.txt)
    endpoint.permission = 'authenticated'
    # described in the OpenAPI document (see web.openapi)
    endpoint.described = True
