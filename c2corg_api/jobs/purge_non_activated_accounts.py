import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import and_

from c2corg_api.models import DBSession
from c2corg_api.models.cache_version import CacheVersion
from c2corg_api.models.document import (
    ArchiveDocument,
    ArchiveDocumentGeometry,
    ArchiveDocumentLocale,
    Document,
    DocumentGeometry,
    DocumentLocale,
)
from c2corg_api.models.document_history import DocumentVersion, HistoryMetaData
from c2corg_api.models.user import Purpose, User
from c2corg_api.models.user_profile import ArchiveUserProfile, UserProfile

log = logging.getLogger(__name__)


def purge_account():
    now = datetime.now(UTC)

    # A plain session on the engine configured on DBSession by
    # c2corg_api/scripts/jobs/scheduler.py: DBSession itself cannot be committed
    # outside of the transaction manager, and `Session()` alone has no bind.
    with Session(DBSession.get_bind()) as session:

        def delete(cls, attr, ids):
            session.query(cls).filter(attr.in_(ids)).delete(synchronize_session=False)

        ids = (
            session.query(User.id)
            .filter(
                and_(
                    User.email_validated.is_(False),
                    User.validation_nonce.like(Purpose.registration.value + '_%'),
                    User.validation_nonce_expire < now,
                )
            )
            .all()
        )
        ids = [idwrap[0] for idwrap in ids]

        log.info('Deleting %d non activated users: %s', len(ids), ids)
        if len(ids) > 0:
            # the profile of each account is a whole document: remove it, with
            # its archives and its geometry, in the order the foreign keys need
            archive_ids = (
                session.query(ArchiveDocument.id)
                .filter(ArchiveDocument.document_id.in_(ids))
                .scalar_subquery()
            )
            delete(DocumentVersion, DocumentVersion.document_id, ids)
            delete(HistoryMetaData, HistoryMetaData.user_id, ids)
            delete(ArchiveDocumentLocale, ArchiveDocumentLocale.document_id, ids)
            delete(ArchiveDocumentGeometry, ArchiveDocumentGeometry.document_id, ids)
            delete(ArchiveUserProfile, ArchiveUserProfile.id, archive_ids)
            delete(ArchiveDocument, ArchiveDocument.document_id, ids)
            delete(DocumentLocale, DocumentLocale.document_id, ids)
            delete(DocumentGeometry, DocumentGeometry.document_id, ids)
            delete(User, User.id, ids)
            delete(UserProfile, UserProfile.document_id, ids)
            delete(CacheVersion, CacheVersion.document_id, ids)
            delete(Document, Document.document_id, ids)
            session.commit()
