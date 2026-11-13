"""Database session of the FastAPI views."""

from contextlib import contextmanager

from c2corg_api.models import DBSession


@contextmanager
def request_session():
    """Give a view the session, then end it, as pyramid_tm did per request."""
    # Use it inside the view function: the session is per thread, and
    # FastAPI runs a sync view in a single worker thread.
    # What the view did not commit is rolled back.
    try:
        yield DBSession()
    finally:
        DBSession.rollback()
        DBSession.remove()
