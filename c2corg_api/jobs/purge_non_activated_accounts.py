import logging
from datetime import UTC, datetime

from sqlalchemy.sql.expression import and_

from c2corg_api.models import DBSession, commit_or_rollback
from c2corg_api.models.document_history import DocumentVersion, HistoryMetaData
from c2corg_api.models.user import Purpose, User
from c2corg_api.scripts.users.merge import _remove_user_account
from c2corg_api.views.document_delete import remove_from_cache

log = logging.getLogger(__name__)


def purge_account():
    """Remove the accounts whose registration was not validated in time."""
    now = datetime.now(UTC)

    # DBSession is scoped by thread: this job's session is closed at the end
    try:
        with commit_or_rollback(DBSession):
            ids = [
                row[0]
                for row in DBSession.query(User.id).filter(
                    and_(
                        User.email_validated.is_(False),
                        User.validation_nonce.like(Purpose.registration.value + '_%'),
                        User.validation_nonce_expire < now,
                    )
                )
            ]

            log.info('Deleting %d non activated users: %s', len(ids), ids)
            if ids:
                # the versions of the profile and their history metadata
                # refer to the user: removed first
                DBSession.query(DocumentVersion).filter(
                    DocumentVersion.document_id.in_(ids)
                ).delete(synchronize_session=False)
                DBSession.query(HistoryMetaData).filter(
                    HistoryMetaData.user_id.in_(ids)
                ).delete(synchronize_session=False)
                # The user, then the whole profile document. A bulk delete of
                # UserProfile would only remove the user_profiles row, and
                # leave the documents row a polymorphic load fails on.
                for user_id in ids:
                    remove_from_cache(user_id)
                    _remove_user_account(user_id)
    finally:
        DBSession.remove()
