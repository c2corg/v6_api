"""The actions on documents: merge, protect, revert, mask versions, delete."""
# The routes call the functions of views/ through web.compat, with the
# checks their decorators declare (see web.documents.include_document_writes).

from c2corg_api.views.document_delete import delete_document, delete_document_locale
from c2corg_api.views.document_merge import merge_documents
from c2corg_api.views.document_protect import protect_document, unprotect_document
from c2corg_api.views.document_revert import revert_document
from c2corg_api.views.document_version_mask import mask_version, unmask_version
from c2corg_api.web.documents import handler_arguments, include_handler_write

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
]


def include(app):
    """Add the routes of this module to the FastAPI application."""
    for path, http_method, function in WRITES:
        include_handler_write(
            app, path, http_method, function, *handler_arguments(function)
        )
