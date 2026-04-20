"""
FastAPI application entry-point.

Usage (development)
-------------------
::

    uvicorn c2corg_api.app:get_app --factory --host 0.0.0.0 --port 6543 --reload

Or set ``C2CORG_INI`` to point at a different ``.ini`` file.
"""

import logging
import os
from configparser import ConfigParser, ExtendedInterpolation
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

log = logging.getLogger(__name__)


def _load_settings(ini_file: str) -> dict[str, str]:
    """Parse a Paste-Deploy ``.ini`` file and return the ``[app:main]``
    settings dict..
    """
    ini_path = Path(ini_file)

    parser = ConfigParser(interpolation=ExtendedInterpolation())

    # Explicit inheritance instead of PasteDeploy
    common_ini = ini_path.parent / 'common.ini'
    parser.read([common_ini, ini_path])

    settings = dict(parser['app:main'])

    # Explicitly drop PasteDeploy-only key
    settings.pop('use', None)

    return settings


def create_app(*, engine=None) -> FastAPI:
    """Application factory called once at startup.

    Parameters
    ----------
    engine : sqlalchemy.engine.Engine, optional
        Pre-existing SQLAlchemy engine to reuse (e.g. from the test
        harness).  When *None* a new engine is created from the
        ``.ini`` settings.
    """

    # --- resolve the .ini file -------------------------------------------
    ini_file = os.environ.get('C2CORG_INI', 'development.ini')
    log.info('Loading settings from %s', ini_file)
    settings = _load_settings(ini_file)

    # --- FastAPI app -----------------------------------------------------
    fastapi_app = FastAPI(
        title='c2corg API',
        description='Camptocamp.org API – FastAPI + Pyramid transitional',
        version='7.0.0-dev',
    )

    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=['*'],
        allow_methods=['*'],
        allow_headers=['Content-Type'],
    )

    @fastapi_app.exception_handler(HTTPException)
    async def _http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        """Normalise FastAPI ``HTTPException`` responses to the Cornice
        error format that the UI relies on::

            {"status": "error",
             "errors": [{"location": …, "name": …,
                         "description": …}]}

        ``detail`` may be:
        - a dict with ``'errors'`` key  → use as-is (already Cornice-shaped)
        - a plain string               → wrap in a single-element errors list
        """
        detail = exc.detail
        if isinstance(detail, dict) and 'errors' in detail:
            content = {'status': 'error', 'errors': detail['errors']}
        elif isinstance(detail, str):
            content = {
                'status': 'error',
                'errors': [
                    {'location': 'body', 'name': 'Bad Request', 'description': detail}
                ],
            }
        else:
            content = {
                'status': 'error',
                'errors': [
                    {
                        'location': 'body',
                        'name': 'Bad Request',
                        'description': str(detail),
                    }
                ],
            }
        return JSONResponse(status_code=exc.status_code, content=content)

    @fastapi_app.exception_handler(Exception)
    async def _unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Return a proper JSON response for unhandled exceptions.

        Without this, Starlette emits a bare-bones plain-text 500
        that bypasses ``CORSMiddleware``'s response hook — meaning
        the browser hides the error from JavaScript SPA clients.

        We explicitly set the ``Access-Control-Allow-Origin``
        header because Starlette's ``ServerErrorMiddleware``
        intercepts 500 responses before ``CORSMiddleware`` can
        decorate them.

        """
        log.error(
            'Unhandled exception on %s %s: %s',
            request.method,
            request.url.path,
            exc,
            exc_info=True,
        )
        origin = request.headers.get('origin')
        headers = {'Access-Control-Allow-Origin': '*'} if origin else {}
        return JSONResponse(
            status_code=500,
            content={'detail': 'Internal server error'},
            headers=headers,
        )

    @fastapi_app.exception_handler(RequestValidationError)
    async def _validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Return 400 instead of FastAPI's default 422.

        Colander/Cornice (the previous validation layer) returned 400
        for malformed request bodies.  Returning 400 preserves backward
        compatibility for existing API consumers.

        The response body follows the same Cornice error format used
        throughout the API.
        """
        errors = []
        seen_fields = set()
        for error in exc.errors():
            loc = error.get('loc', ())
            # Build a dotted field path, skipping the leading 'body'
            # segment that Pydantic injects for JSON body errors.
            parts = [p for p in loc if p != 'body']

            # When a scalar item inside a list fails validation
            # (e.g. an invalid enum value at activities[1]), pydantic
            # reports the loc as ('activities', 1).  Collapse such
            # paths to just the parent field name ('activities') so
            # that API consumers can match on the top-level field,
            # matching the Cornice/Pyramid pydantic validator behaviour.
            if len(parts) == 2 and isinstance(parts[1], int):
                parts = parts[:1]

            field = '.'.join(str(p) for p in parts) if parts else 'body'

            # Avoid duplicate errors for the same collapsed field
            if field in seen_fields:
                continue
            seen_fields.add(field)

            msg = error.get('msg', '')
            if msg == 'Field required':
                msg = 'Required'
            if msg.startswith('Value error, '):
                msg = msg[len('Value error, ') :]

            errors.append({'location': 'body', 'name': field, 'description': msg})

        return JSONResponse(
            status_code=400, content={'status': 'error', 'errors': errors}
        )

    # --- shared database engine ------------------------------------------
    if engine is None:
        from sqlalchemy import engine_from_config

        engine = engine_from_config(settings, 'sqlalchemy.')

    from c2corg_api.database import configure_db

    configure_db(engine)

    # --- dogpile.cache (Redis) -------------------------------------------
    from c2corg_api.caching import configure_caches

    configure_caches(settings)

    # --- anonymous user for xreports ------------------------------------
    from c2corg_api.routers.helpers.document_crud import configure_anonymous

    configure_anonymous(settings)

    # --- FastAPI routers -------------------------------------------------
    from c2corg_api.routers.book import router as book_router

    fastapi_app.include_router(book_router)

    from c2corg_api.routers.article import router as article_router

    fastapi_app.include_router(article_router)

    from c2corg_api.routers.xreport import router as xreport_router

    fastapi_app.include_router(xreport_router)

    from c2corg_api.routers.image import router as image_router

    fastapi_app.include_router(image_router)

    from c2corg_api.routers.route import router as route_router

    fastapi_app.include_router(route_router)

    from c2corg_api.routers.area import router as area_router

    fastapi_app.include_router(area_router)

    from c2corg_api.routers.coverage import router as coverage_router

    fastapi_app.include_router(coverage_router)

    from c2corg_api.routers.outing import router as outing_router

    fastapi_app.include_router(outing_router)

    from c2corg_api.routers.topo_map import router as topo_map_router

    fastapi_app.include_router(topo_map_router)

    from c2corg_api.routers.waypoint import router as waypoint_router

    fastapi_app.include_router(waypoint_router)

    from c2corg_api.routers.user_profile import router as user_profile_router

    fastapi_app.include_router(user_profile_router)

    from c2corg_api.routers.health import configure_health
    from c2corg_api.routers.health import router as health_router

    fastapi_app.include_router(health_router)
    configure_health(settings)

    from c2corg_api.routers.association_history import (
        router as association_history_router,
    )

    fastapi_app.include_router(association_history_router)

    from c2corg_api.routers.association import configure_association_router
    from c2corg_api.routers.association import router as association_router

    fastapi_app.include_router(association_router)

    from c2corg_api.routers.user_preferences import router as user_preferences_router

    fastapi_app.include_router(user_preferences_router)

    from c2corg_api.routers.cooker import router as cooker_router

    fastapi_app.include_router(cooker_router)

    from c2corg_api.routers.document_changes import router as document_changes_router

    fastapi_app.include_router(document_changes_router)

    from c2corg_api.routers.document_history import router as document_history_router

    fastapi_app.include_router(document_history_router)

    from c2corg_api.routers.document_protect import router as document_protect_router

    fastapi_app.include_router(document_protect_router)

    from c2corg_api.routers.document_tag import configure_tag_router
    from c2corg_api.routers.document_tag import router as document_tag_router

    fastapi_app.include_router(document_tag_router)

    from c2corg_api.routers.document_version_mask import (
        router as document_version_mask_router,
    )

    fastapi_app.include_router(document_version_mask_router)

    from c2corg_api.routers.document_merge import configure_merge_router
    from c2corg_api.routers.document_merge import router as document_merge_router

    fastapi_app.include_router(document_merge_router)

    from c2corg_api.routers.document_delete import configure_delete_router
    from c2corg_api.routers.document_delete import router as document_delete_router

    fastapi_app.include_router(document_delete_router)

    from c2corg_api.routers.document_revert import router as document_revert_router

    fastapi_app.include_router(document_revert_router)

    from c2corg_api.routers.feed import configure_feed_router
    from c2corg_api.routers.feed import router as feed_router

    fastapi_app.include_router(feed_router)

    from c2corg_api.routers.forum import configure_forum_router
    from c2corg_api.routers.forum import router as forum_router

    fastapi_app.include_router(forum_router)

    from c2corg_api.routers.navitia import router as navitia_router

    fastapi_app.include_router(navitia_router)

    from c2corg_api.routers.search import router as search_router

    fastapi_app.include_router(search_router)

    from c2corg_api.routers.sitemap import router as sitemap_router

    fastapi_app.include_router(sitemap_router)

    from c2corg_api.routers.sitemap_xml import router as sitemap_xml_router

    fastapi_app.include_router(sitemap_xml_router)

    from c2corg_api.routers.sso import configure_sso_router
    from c2corg_api.routers.sso import router as sso_router

    fastapi_app.include_router(sso_router)

    from c2corg_api.routers.user import configure_user_router
    from c2corg_api.routers.user import router as user_router

    fastapi_app.include_router(user_router)

    from c2corg_api.routers.user_account import configure_user_account_router
    from c2corg_api.routers.user_account import router as user_account_router

    fastapi_app.include_router(user_account_router)

    from c2corg_api.routers.user_block import configure_user_block_router
    from c2corg_api.routers.user_block import router as user_block_router

    fastapi_app.include_router(user_block_router)

    from c2corg_api.routers.user_follow import router as user_follow_router

    fastapi_app.include_router(user_follow_router)

    from c2corg_api.routers.user_mailinglists import router as user_mailinglists_router

    fastapi_app.include_router(user_mailinglists_router)

    from c2corg_api.routers.stoparea import router as stoparea_router

    fastapi_app.include_router(stoparea_router)

    from c2corg_api.routers.waypoint_stoparea import router as waypoint_stoparea_router

    fastapi_app.include_router(waypoint_stoparea_router)

    # --- routers queue config ---------------------------------
    from c2corg_api.search import get_queue_config

    queue_config = get_queue_config(settings)
    configure_association_router(queue_config)
    configure_tag_router(queue_config)
    configure_merge_router(queue_config)
    configure_delete_router(queue_config)

    configure_feed_router(settings)
    configure_forum_router(settings)
    configure_sso_router(settings)
    configure_user_router(settings)
    configure_user_account_router(settings)
    configure_user_block_router(settings)

    log.info('FastAPI app ready')
    return fastapi_app


# module-level instance so that ``uvicorn c2corg_api.app:app`` works.
# Guarded so that importing the module for tests or introspection
# does not immediately require a running database.
app: FastAPI | None = None


def get_app() -> FastAPI:
    """Return the singleton FastAPI application, creating it on first call."""
    global app
    if app is None:
        app = create_app()
    return app
