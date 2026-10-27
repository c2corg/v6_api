"""The histories: of a document, of the document changes, of the associations."""
# The routes call the view classes of views/ through the adapter of
# web.compat, as the document routes do (#2365).

from typing import Annotated

from fastapi import Depends, Request

from c2corg_api.views.association_history import HistoryAssociationRest
from c2corg_api.views.document_changes import ChangesDocumentRest
from c2corg_api.views.document_history import HistoryDocumentRest
from c2corg_api.views.validation import (
    validate_document_id_not_required,
    validate_id,
    validate_lang,
    validate_pagination,
    validate_simple_token_pagination,
    validate_user_id_not_required,
)
from c2corg_api.web.auth import CurrentUser, current_user
from c2corg_api.web.compat import serve_view

User = Annotated[CurrentUser | None, Depends(current_user)]


def include(app):
    """Add the routes of this module to the FastAPI application."""
    methods = ['GET', 'HEAD']
    # a numeric id only, as the document routes (see web.documents)
    app.add_api_route(
        '/document/{id:int}/history/{lang}', document_history, methods=methods
    )
    app.add_api_route('/documents/changes', document_changes, methods=methods)
    app.add_api_route('/associations-history', associations_history, methods=methods)


def document_history(request: Request, user: User):
    """Return the versions of a document in a language."""
    return serve_view(request, user, [validate_id, validate_lang], HistoryDocumentRest)


def document_changes(request: Request, user: User):
    """Return the last changes of the documents, or of the documents of a user."""
    return serve_view(
        request,
        user,
        [validate_simple_token_pagination, validate_user_id_not_required],
        ChangesDocumentRest,
    )


def associations_history(request: Request, user: User):
    """Return the last changes of the associations, of a document or a user."""
    return serve_view(
        request,
        user,
        [
            validate_document_id_not_required,
            validate_pagination,
            validate_user_id_not_required,
        ],
        HistoryAssociationRest,
    )
