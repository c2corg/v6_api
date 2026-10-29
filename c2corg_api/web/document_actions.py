"""The actions on documents: merge, protect, revert, mask versions, delete."""
# The routes call the view classes of views/ through web.compat, with the
# checks their Cornice decorators declare (see web.documents.include_write).

from c2corg_api.views.document_delete import (
    DeleteDocumentLocaleRest,
    DeleteDocumentRest,
)
from c2corg_api.views.document_merge import MergeDocumentRest
from c2corg_api.views.document_protect import (
    DocumentProtectRest,
    DocumentUnprotectRest,
)
from c2corg_api.views.document_revert import DocumentRevertRest
from c2corg_api.views.document_version_mask import VersionMaskRest, VersionUnmaskRest
from c2corg_api.web.documents import include_write

# (path, HTTP method, view class, method of the view class); a numeric id
# only, as the document routes
WRITES = [
    ('/documents/merge', 'POST', MergeDocumentRest, 'post'),
    ('/documents/protect', 'POST', DocumentProtectRest, 'post'),
    ('/documents/unprotect', 'POST', DocumentUnprotectRest, 'post'),
    ('/documents/revert', 'POST', DocumentRevertRest, 'post'),
    ('/versions/mask', 'POST', VersionMaskRest, 'post'),
    ('/versions/unmask', 'POST', VersionUnmaskRest, 'post'),
    ('/documents/delete/{id:int}', 'DELETE', DeleteDocumentRest, 'delete'),
    ('/documents/delete/{id:int}/{lang}', 'DELETE', DeleteDocumentLocaleRest, 'delete'),
]


def include(app):
    """Add the routes of this module to the FastAPI application."""
    for path, http_method, view_class, method in WRITES:
        include_write(app, path, http_method, view_class, method)
