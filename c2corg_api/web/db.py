"""Database session of the FastAPI views."""

from contextlib import contextmanager

import transaction

from c2corg_api.models import DBSession


@contextmanager
def request_session():
    """Give a view the session, then end it, as pyramid_tm did per request."""
    # Use it inside the view function: the session is per thread, and
    # FastAPI runs a sync view in a single worker thread.
    try:
        yield DBSession()
    finally:
        transaction.abort()
        DBSession.remove()
