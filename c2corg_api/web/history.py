"""The histories: of a document, of the document changes, of the associations."""
# The routes call the view classes of views/ through the adapter of
# web.compat, as the document routes do (#2365). Their parameters are typed
# (#2512).

from typing import Annotated

from fastapi import Depends, Query, Request

from c2corg_api.views.association_history import (
    LIMIT_DEFAULT,
    LIMIT_MAX,
    HistoryAssociationRest,
)
from c2corg_api.views.document_changes import ChangesDocumentRest
from c2corg_api.views.document_history import HistoryDocumentRest
from c2corg_api.views.feed import MAX_PAGE_LIMIT
from c2corg_api.web.auth import CurrentUser, current_user
from c2corg_api.web.compat import serve_view, typed_values
from c2corg_api.web.params import (
    ChangesToken,
    DocumentId,
    Limit,
    Offset,
    PathLang,
    integer,
)

User = Annotated[CurrentUser | None, Depends(current_user)]
UserFilter = Annotated[
    integer('u') | None, Query(description='Only the changes of this user (id).')
]


def include(app):
    """Add the routes of this module to the FastAPI application."""
    methods = ['GET', 'HEAD']
    # a numeric id only, as the document routes (see web.documents)
    app.add_api_route(
        '/document/{id:int}/history/{lang}',
        document_history,
        methods=methods,
        operation_id='get_document_history',
        tags=['history'],
    )
    app.add_api_route(
        '/documents/changes',
        document_changes,
        methods=methods,
        operation_id='list_document_changes',
        tags=['history'],
    )
    app.add_api_route(
        '/associations-history',
        associations_history,
        methods=methods,
        operation_id='list_association_changes',
        tags=['history'],
    )


def document_history(request: Request, user: User, id: DocumentId, lang: PathLang):
    """Return the versions of a document in a language."""
    validated = {'id': id, 'lang': lang}
    return serve_view(request, user, [typed_values(validated)], HistoryDocumentRest)


def document_changes(
    request: Request,
    user: User,
    limit: Annotated[
        Limit | None,
        Query(
            description=f'How many changes: 30 by default, {MAX_PAGE_LIMIT} at most.'
        ),
    ] = None,
    token: Annotated[
        ChangesToken | None,
        Query(description='The `pagination_token` of the previous page.'),
    ] = None,
    u: UserFilter = None,
):
    """Return the last changes of the documents, or of the documents of a user."""
    # outings and profiles are left out
    validated = {'limit': limit, 'token_id': token, 'u': u}
    return serve_view(request, user, [typed_values(validated)], ChangesDocumentRest)


def associations_history(
    request: Request,
    user: User,
    d: Annotated[
        integer('d') | None,
        Query(description='Only the associations of this document (id).'),
    ] = None,
    offset: Annotated[
        Offset | None, Query(description='The first change, from 0.')
    ] = None,
    limit: Annotated[
        Limit | None,
        Query(
            description=f'How many changes: {LIMIT_DEFAULT} by default, '
            f'{LIMIT_MAX} at most.'
        ),
    ] = None,
    u: UserFilter = None,
):
    """Return the last changes of the associations, of a document or a user."""
    validated = {'d': d, 'offset': offset, 'limit': limit, 'u': u}
    return serve_view(request, user, [typed_values(validated)], HistoryAssociationRest)


for endpoint in (document_history, document_changes, associations_history):
    # described in the OpenAPI document (see web.openapi)
    endpoint.described = True
