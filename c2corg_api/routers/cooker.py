"""
FastAPI Cooker router.

Provides ``/v2/cooker`` — a stateless endpoint that converts
Markdown locale fields to HTML.

Security hardening over the legacy Pyramid view
------------------------------------------------
* **Body size cap**: rejects payloads with more than ``MAX_KEYS`` keys or
  individual values longer than ``MAX_VALUE_LENGTH`` characters to prevent
  DoS through expensive Markdown parsing.
* **Type enforcement**: only ``str`` values are fed to the Markdown parser;
  non-string values are passed through unchanged, preventing
  ``parse_code`` from receiving unexpected types.
* **Output sanitisation** is already handled inside ``parse_code`` which
  pipes everything through ``bleach`` before returning.
"""

import logging

from fastapi import APIRouter, HTTPException, Request

from c2corg_api.routers.helpers.markdown import cook

log = logging.getLogger(__name__)

router = APIRouter(prefix='/v2', tags=['cooker'])

# ── Limits ───────────────────────────────────────────────────────
MAX_KEYS = 15
MAX_VALUE_LENGTH = 10_000  # ~10 KB per field — a large paragraph


@router.post('/cooker')
async def cooker(request: Request):
    """Stateless Markdown → HTML conversion.

    Accepts a flat JSON object whose values are Markdown strings.
    Returns the same object with values converted to HTML, except
    for keys listed in ``NOT_MARKDOWN_PROPERTY`` which are returned
    unchanged.
    """
    # --- parse & validate body ----------------------------------------
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail='Invalid JSON body')

    if not isinstance(body, dict):
        raise HTTPException(
            status_code=400, detail='Request body must be a JSON object'
        )

    if len(body) > MAX_KEYS:
        raise HTTPException(status_code=400, detail=f'Too many keys (max {MAX_KEYS})')

    for key, value in body.items():
        if isinstance(value, str) and len(value) > MAX_VALUE_LENGTH:
            raise HTTPException(
                status_code=400,
                detail=f"Value for '{key}' exceeds maximum length "
                f'({MAX_VALUE_LENGTH} characters)',
            )

    # --- cook ---------------------------------------------------------
    return cook(body)
