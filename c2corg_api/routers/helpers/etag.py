"""
FastAPI equivalent of ``c2corg_api.views.etag_cache``.

Pyramid's version raises ``HTTPNotModified``; FastAPI uses a 304 response
via ``HTTPException``.

The ``Cache-Control`` forwarding from the Pyramid version is preserved:
if the response already has a ``Cache-Control`` header, it is copied
onto the 304 so the browser keeps respecting it.
"""

import logging

from fastapi import HTTPException, Request, Response

log = logging.getLogger(__name__)


def etag_cache(request: Request, response: Response, key: str):
    """Check ``If-None-Match`` and handle ETag caching.

    * **ETag match** → raise ``HTTPException(304)`` with the ``ETag``
      (and ``Cache-Control`` if present).  The browser uses its local
      copy.
    * **No match** → set the ``ETag`` header on the outgoing
      ``response`` so the browser can cache it.

    Parameters
    ----------
    request
        Incoming FastAPI / Starlette ``Request``.
    response
        Outgoing ``Response`` — used to set headers when the response
        is *not* 304.  Inject it as a route parameter or via
        ``Depends``.
    key
        Version string used as weak ETag value (matches the dogpile
        cache key / ``CacheVersion.version`` composite).
    """
    # always use a weak validator, same as Pyramid version
    etag = 'W/"%s"' % key
    if_none_match = request.headers.get('if-none-match', '')

    if str(key) in if_none_match:
        headers = {'ETag': etag}
        # preserve Cache-Control if it was already set (e.g. "private")
        cc = response.headers.get('Cache-Control')
        if cc:
            headers['Cache-Control'] = cc

        log.debug('ETag match, returning 304 HTTP Not Modified Response')
        raise HTTPException(status_code=304, headers=headers)
    else:
        response.headers['ETag'] = etag
        log.debug("ETag didn't match, returning response object")


def set_private_cache_header(response: Response):
    """Mark the response as ``Cache-Control: private``.

    FastAPI equivalent of ``c2corg_api.views.set_private_cache_header``.
    """
    response.headers['Cache-Control'] = 'private'
