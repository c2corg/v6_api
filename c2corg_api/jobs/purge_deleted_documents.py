import logging

from sqlalchemy import delete
from sqlalchemy.orm import Session

from c2corg_api.models import DBSession
from c2corg_api.models.deleted_document import DeletedDocument
from c2corg_api.views.document_trash import expired_before

log = logging.getLogger(__name__)


def purge_deleted_documents():
    """Remove the deleted documents kept longer than the retention."""
    # the restored ones too: kept until then to tell who restored what
    # A plain session on the engine configured on DBSession, as purge_token.
    with Session(DBSession.get_bind()) as session:
        count = session.execute(
            delete(DeletedDocument).where(DeletedDocument.deleted_at < expired_before())
        ).rowcount
        log.info('Purging %d deleted documents', count)
        session.commit()
