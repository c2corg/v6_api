"""The sitemaps: as JSON for the UI, and as XML for the search engines."""
# The routes call the view classes of views/ through the adapter of
# web.compat, as the document routes do (#2365). Their parameters are typed
# (#2512).

from typing import Annotated

from fastapi import Depends, Path, Request

from c2corg_api.views.sitemap import SitemapRest
from c2corg_api.views.sitemap_xml import SitemapXml
from c2corg_api.web.auth import CurrentUser, current_user
from c2corg_api.web.compat import serve_view, typed_values
from c2corg_api.web.params import DocType, natural

User = Annotated[CurrentUser | None, Depends(current_user)]
DocumentType = Annotated[DocType, Path(description='The document type.')]
Page = Annotated[natural('i'), Path(description='The number of the sitemap, from 0.')]


def include(app):
    """Add the routes of this module to the FastAPI application."""
    methods = ['GET', 'HEAD']
    for path, endpoint, summary in (
        ('/sitemaps', sitemap_index, 'The sitemaps of each document type.'),
        ('/sitemaps/{doc_type}/{i}', sitemap, 'The documents of a sitemap.'),
        ('/sitemaps.xml', sitemap_index_xml, 'The sitemap index, in XML.'),
        ('/sitemaps.xml/{doc_type}/{i}.xml', sitemap_xml, 'A sitemap, in XML.'),
    ):
        app.add_api_route(
            path,
            endpoint,
            methods=methods,
            operation_id=endpoint.__name__,
            summary=summary,
            tags=['sitemaps'],
        )


def sitemap_index(request: Request, user: User):
    """Return the URLs of the sitemaps."""
    return serve_view(request, user, [], SitemapRest, 'collection_get')


# `i` before `doc_type`: its error comes first, as its validator did
def sitemap(request: Request, user: User, i: Page, doc_type: DocumentType):
    """Return the pages of a sitemap."""
    validated = {'i': i, 'doc_type': doc_type}
    return serve_view(request, user, [typed_values(validated)], SitemapRest)


def sitemap_index_xml(request: Request, user: User):
    """Return the sitemap index file."""
    return serve_view(request, user, [], SitemapXml, 'collection_get')


def sitemap_xml(request: Request, user: User, i: Page, doc_type: DocumentType):
    """Return a sitemap file."""
    validated = {'i': i, 'doc_type': doc_type}
    return serve_view(request, user, [typed_values(validated)], SitemapXml)


for endpoint in (sitemap_index, sitemap, sitemap_index_xml, sitemap_xml):
    # described in the OpenAPI document (see web.openapi)
    endpoint.described = True
