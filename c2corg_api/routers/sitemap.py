"""
FastAPI Sitemap router (JSON).

Provides:
  - ``/v2/sitemaps``                     — sitemap index
  - ``/v2/sitemaps/{doc_type}/{i}``      — sitemap page

Mirrors ``c2corg_api.views.sitemap``.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from c2corg_api.database import get_db
from c2corg_api.models.common import document_types
from c2corg_api.routers.helpers.sitemap import get_cache_key as _get_cache_key
from c2corg_api.routers.helpers.sitemap import get_sitemap as _get_sitemap
from c2corg_api.routers.helpers.sitemap import get_sitemap_index as _get_sitemap_index

log = logging.getLogger(__name__)

router = APIRouter(prefix='/v2', tags=['sitemap'])


@router.get('/sitemaps')
def get_sitemap_index(
    request: Request, response: Response, db: Session = Depends(get_db)
):
    """Return the sitemap index (list of sitemap page URLs)."""
    from c2corg_api.caching import cache_sitemap, get_or_create

    cache_key = _get_cache_key()

    etag = 'W/"%s"' % cache_key
    if etag in (request.headers.get('if-none-match') or ''):
        return Response(status_code=304, headers={'ETag': etag})

    result = get_or_create(cache_sitemap, cache_key, _get_sitemap_index)
    response.headers['ETag'] = etag
    return result


@router.get('/sitemaps/{doc_type}/{i}')
def get_sitemap_page(
    doc_type: str,
    i: str,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Return a sitemap page for a given type and page number."""
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
        page_num = int(i)
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

    import functools

    from c2corg_api.caching import cache_sitemap, get_or_create

    cache_key = _get_cache_key(doc_type, page_num)

    etag = 'W/"%s"' % cache_key
    if etag in (request.headers.get('if-none-match') or ''):
        return Response(status_code=304, headers={'ETag': etag})

    try:
        result = get_or_create(
            cache_sitemap,
            cache_key,
            functools.partial(_get_sitemap, doc_type, page_num),
        )
    except Exception:
        # _get_sitemap raises HTTPNotFound when no pages
        raise HTTPException(status_code=404, detail='Not Found')

    response.headers['ETag'] = etag
    return result
