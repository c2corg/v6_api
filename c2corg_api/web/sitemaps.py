"""The sitemaps: as JSON for the UI, and as XML for the search engines."""
# The routes call the view classes of views/ through the adapter of
# web.compat, as the document routes do (#2365).

from typing import Annotated

from fastapi import Depends, Request

from c2corg_api.views.sitemap import SitemapRest
from c2corg_api.views.sitemap import validate_page as validate_json_page
from c2corg_api.views.sitemap_xml import SitemapXml
from c2corg_api.views.sitemap_xml import validate_page as validate_xml_page
from c2corg_api.views.validation import validate_document_type
from c2corg_api.web.auth import CurrentUser, current_user
from c2corg_api.web.compat import serve_view

User = Annotated[CurrentUser | None, Depends(current_user)]


def include(app):
    """Add the routes of this module to the FastAPI application."""
    methods = ['GET', 'HEAD']
    app.add_api_route('/sitemaps', sitemap_index, methods=methods)
    app.add_api_route('/sitemaps/{doc_type}/{i}', sitemap, methods=methods)
    app.add_api_route('/sitemaps.xml', sitemap_index_xml, methods=methods)
    app.add_api_route('/sitemaps.xml/{doc_type}/{i}.xml', sitemap_xml, methods=methods)


def sitemap_index(request: Request, user: User):
    """Return the URLs of the sitemaps."""
    return serve_view(request, user, [], SitemapRest, 'collection_get')


def sitemap(request: Request, user: User):
    """Return the pages of a sitemap."""
    validators = [validate_json_page, validate_document_type]
    return serve_view(request, user, validators, SitemapRest)


def sitemap_index_xml(request: Request, user: User):
    """Return the sitemap index file."""
    return serve_view(request, user, [], SitemapXml, 'collection_get')


def sitemap_xml(request: Request, user: User):
    """Return a sitemap file."""
    validators = [validate_xml_page, validate_document_type]
    return serve_view(request, user, validators, SitemapXml)
