from c2corg_api.models.user import User, Purpose
from c2corg_api.models.document import DocumentLocale
from c2corg_api.models.document_history import DocumentVersion, HistoryMetaData
from c2corg_api.models.user_profile import UserProfile
from datetime import datetime
from sqlalchemy.sql.expression import and_
from sqlalchemy.orm import sessionmaker

import logging
log = logging.getLogger(__name__)


def purge_account(test_session=None):
    now = datetime.utcnow()
    session = sessionmaker()() if not test_session else test_session

    def delete(cls, attr, ids):
        session.query(cls).filter(attr.in_(ids)).delete(
            synchronize_session=False)

    try:
        ids = session.query(User.id).filter(and_(
             User.email_validated.is_(False),
             User.validation_nonce.like(Purpose.registration.value + '_%'),
             User.validation_nonce_expire < now)).all()
        ids = [idwrap[0] for idwrap in ids]

        log.info('Deleting %d non activated users: %s', len(ids), ids)
        if len(ids) > 0:
            delete(DocumentVersion, DocumentVersion.document_id, ids)
            delete(HistoryMetaData, HistoryMetaData.user_id, ids)
            delete(User, User.id, ids)
            delete(UserProfile, UserProfile.document_id, ids)
            delete(DocumentLocale, DocumentLocale.document_id, ids)
            session.commit()
    finally:
        if not test_session:
            session.close()
