"""Serve a read or a write request with a view function."""
# The order of the checks: the rate limiting (writes), the content type and
# the permission (web.checks), the origin and the validators, then the view;
# the writes are committed or rolled back as pyramid_tm did.

from starlette.concurrency import run_in_threadpool

from c2corg_api.httpexceptions import HTTPError, HTTPRedirection
from c2corg_api.models import DBSession
from c2corg_api.models.user import AccountNotValidated
from c2corg_api.web.answers import (
    account_not_validated,
    call_view,
    http_error,
    redirection,
    render,
    run_view,
)
from c2corg_api.web.checks import refusal, validate_origin
from c2corg_api.web.db import request_session
from c2corg_api.web.errors import error_response
from c2corg_api.web.request import ValidatedRequest


def typed_values(values):
    """Return a validator giving the views the typed parameters of a route."""

    # the views read them in request.validated, where the validators of
    # views/validation.py put them: only those given
    def validator(request, **kwargs):
        request.validated.update((k, v) for k, v in values.items() if v is not None)

    return validator


def validate_query(request, *validators, user=None):
    """Run the validators; return (adapted request, error answer or None)."""
    adapted = ValidatedRequest(request, user)
    try:
        for validator in (validate_origin, *validators):
            validator(adapted)
    except HTTPError as e:
        # a validator may raise, as the views do (e.g. an invalid waypoint id)
        return adapted, http_error(e)
    if adapted.errors:
        return adapted, error_response(adapted.errors, adapted.errors.status)
    return adapted, None


def serve_read(request, user, validators, handler, permission=None, content_types=None):
    """Answer a read request with a handler of the validated request."""
    # `handler(request)` returns the answer; its `view_name` names it in the
    # 403 answers, as Pyramid named the view
    refused = refusal(request, user, handler.view_name, permission, content_types)
    if refused is not None:
        return refused
    adapted, error = validate_query(request, *validators, user=user)
    if error is not None:
        return error
    with request_session():
        return run_view(adapted, lambda: handler(adapted))


async def serve_write(
    request,
    user,
    validators,
    handler,
    permission=None,
    content_types=None,
):
    """Answer a write request with a handler of the validated request."""
    # `handler(request)` returns the answer; its `view_name` names it in the
    # 403 answers, as Pyramid named the view
    # The body is read here, then the view runs in a worker thread, as the
    # sync views do.
    body = await request.body()
    return await run_in_threadpool(
        _serve_write,
        request,
        user,
        body,
        validators,
        handler,
        permission,
        content_types,
    )


def _serve_write(request, user, body, validators, handler, permission, content_types):
    # As Pyramid with pyramid_tm, one transaction for the request: what the
    # request raises is rolled back (the 415 and the 403, an HTTP error of a
    # validator or of the view, a bug), what it returns is committed (the
    # validation errors, the answer of the view, and the 429 of the rate
    # limiting with its counters).
    from c2corg_api.security.rate_limiting import rate_limit_error
    from c2corg_api.views import invalid_json_body

    adapted = ValidatedRequest(request, user, body=body)
    with request_session():
        # the rate limiting runs first, as its tween did: before the content
        # type, the permission and the validators
        error = rate_limit_error(adapted, adapted.registry.settings)
        if error is not None:
            DBSession.commit()
            return http_error(error)
        refused = refusal(request, user, handler.view_name, permission, content_types)
        if refused is not None:
            return refused
        try:
            for validator in (validate_origin, *validators):
                validator(adapted)
            if adapted.errors:
                DBSession.commit()
                return error_response(adapted.errors, adapted.errors.status)
            result = call_view(adapted, lambda: handler(adapted))
        except HTTPRedirection as e:
            return redirection(e)
        except HTTPError as e:
            return http_error(e)
        except AccountNotValidated as e:
            return account_not_validated(e)
        except Exception:
            # a view reading an invalid JSON body fails on it: an error of the
            # client, answered as the catch-all error view of Pyramid does
            reason = invalid_json_body(adapted)
            if reason is None:
                raise
            return error_response([('body', '', f'Invalid JSON: {reason}')])
        if adapted.errors:
            # as Cornice: the errors the view itself adds are the answer
            # (e.g. a failed login, 401), returned and so committed
            DBSession.commit()
            return error_response(adapted.errors, adapted.errors.status)
        response = render(adapted, result)
        DBSession.commit()
        return response
