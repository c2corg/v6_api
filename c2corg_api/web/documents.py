"""The read routes of the documents: listing, document, info and version."""
# The routes call the view classes of views/ through the adapter of
# web.compat: the logic (caching, ETags, locales, associations, the listing
# filters) and the checks stay the same while the routes move (#2365).

from typing import Annotated

from fastapi import Depends, Request

from c2corg_api.views.validation import (
    validate_cook_param,
    validate_id,
    validate_lang,
    validate_lang_param,
    validate_pagination,
    validate_preferred_lang_param,
    validate_version_id,
)
from c2corg_api.web.auth import CurrentUser, current_user
from c2corg_api.web.compat import run_view, validate_query
from c2corg_api.web.db import request_session

User = Annotated[CurrentUser | None, Depends(current_user)]


def include_document_type(app, prefix, rest, version_rest=None, info_rest=None):
    """Add the read routes of a document type, served by its view classes."""

    def call(request, user, validators, view_class, method='get'):
        adapted, error = validate_query(request, *validators, user=user)
        if error is not None:
            return error
        with request_session():
            view = getattr(view_class(adapted), method)
            return run_view(adapted, view)

    def listing(request: Request, user: User):
        return call(
            request,
            user,
            [validate_pagination, validate_preferred_lang_param],
            rest,
            'collection_get',
        )

    def document(request: Request, user: User):
        return call(
            request,
            user,
            [validate_id, validate_lang_param, validate_cook_param],
            rest,
        )

    methods = ['GET', 'HEAD']
    app.add_api_route(f'/{prefix}', listing, methods=methods)
    app.add_api_route(f'/{prefix}/{{id}}', document, methods=methods)

    if info_rest is not None:

        def info(request: Request, user: User):
            return call(request, user, [validate_id, validate_lang], info_rest)

        app.add_api_route(f'/{prefix}/{{id}}/{{lang}}/info', info, methods=methods)

    if version_rest is not None:

        def version(request: Request, user: User):
            return call(
                request,
                user,
                [validate_id, validate_lang, validate_version_id],
                version_rest,
            )

        app.add_api_route(
            f'/{prefix}/{{id}}/{{lang}}/{{version_id}}', version, methods=methods
        )


def include(app):
    """Add the document routes moved to FastAPI."""
    from c2corg_api.views.area import AreaInfoRest, AreaRest, AreaVersionRest
    from c2corg_api.views.article import (
        ArticleRest,
        ArticlesInfoRest,
        ArticlesVersionRest,
    )
    from c2corg_api.views.book import BookRest, BooksInfoRest, BooksVersionRest
    from c2corg_api.views.coverage import CoverageRest
    from c2corg_api.views.topo_map import TopoMapInfoRest, TopoMapRest

    include_document_type(app, 'books', BookRest, BooksVersionRest, BooksInfoRest)
    include_document_type(
        app, 'articles', ArticleRest, ArticlesVersionRest, ArticlesInfoRest
    )
    include_document_type(app, 'areas', AreaRest, AreaVersionRest, AreaInfoRest)
    # maps have no version route, coverages neither version nor info
    include_document_type(app, 'maps', TopoMapRest, info_rest=TopoMapInfoRest)
    include_document_type(app, 'coverages', CoverageRest)
