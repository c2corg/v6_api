import logging

from sqlalchemy.orm import Session

from c2corg_api.models import DBSession

log = logging.getLogger(__name__)


def increment_documents_views(view_counter):
    """Add the views counted in Redis to the `view_count` of the documents."""
    # A plain session on the engine configured on DBSession by
    # c2corg_api/scripts/jobs/scheduler.py, as purge_token does.
    with Session(DBSession.get_bind()) as session:
        return view_counter.flush(session)
