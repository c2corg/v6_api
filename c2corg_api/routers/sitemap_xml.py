"""
FastAPI Sitemap XML router.

Provides:
  - ``/v2/sitemaps.xml``                        — sitemap index XML
  - ``/v2/sitemaps.xml/{doc_type}/{i}.xml``      — sitemap page XML

Mirrors ``c2corg_api.views.sitemap_xml``.
"""

import functools
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from c2corg_api.database import get_db
from c2corg_api.models.common import document_types
from c2corg_api.routers.helpers.sitemap_xml import get_cache_key as _get_cache_key
from c2corg_api.routers.helpers.sitemap_xml import get_sitemap as _get_sitemap
from c2corg_api.routers.helpers.sitemap_xml import (
    get_sitemap_index as _get_sitemap_index,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix='/v2', tags=['sitemap-xml'])


@router.get('/sitemaps.xml')
def get_sitemap_xml_index(request: Request, db: Session = Depends(get_db)):
    """Return the sitemap index as XML."""
    from c2corg_api.caching import cache_sitemap_xml, get_or_create

    cache_key = _get_cache_key()

    etag = 'W/"%s"' % cache_key
    if etag in (request.headers.get('if-none-match') or ''):
        return Response(status_code=304, headers={'ETag': etag})

    content = get_or_create(cache_sitemap_xml, cache_key, _get_sitemap_index)
    return Response(content=content, media_type='text/xml', headers={'ETag': etag})


@router.get('/sitemaps.xml/{doc_type}/{filename}')
def get_sitemap_xml_page(
    doc_type: str, filename: str, request: Request, db: Session = Depends(get_db)
):
    """Return a sitemap page as XML for a given type and page number."""
    # Strip .xml suffix from filename
    if filename.endswith('.xml'):
        page_str = filename[:-4]
    else:
        page_str = filename

    # Validate doc_type
    if doc_type not in document_types.ALL:
        raise HTTPException(
            status_code=400,
            detail={
                'status': 'error',
                'errors': [
                    {
                        'location': 'querystring',
                        'name': 'doc_type',
                        'description': 'invalid doc_type',
                    }
                ],
            },
        )

    # Validate page number
    try:
        page_num = int(page_str)
        if page_num < 0:
            raise ValueError
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=400,
            detail={
                'status': 'error',
                'errors': [
                    {'location': 'querystring', 'name': 'i', 'description': 'invalid i'}
                ],
            },
        )

    from c2corg_api.caching import cache_sitemap_xml, get_or_create

    cache_key = _get_cache_key(doc_type, page_num)

    etag = 'W/"%s"' % cache_key
    if etag in (request.headers.get('if-none-match') or ''):
        return Response(status_code=304, headers={'ETag': etag})

    try:
        content = get_or_create(
            cache_sitemap_xml,
            cache_key,
            functools.partial(_get_sitemap, doc_type, page_num),
        )
    except Exception:
        raise HTTPException(status_code=404, detail='Not Found')

    return Response(content=content, media_type='text/xml', headers={'ETag': etag})
