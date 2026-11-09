from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.sql.functions import func

from c2corg_api.models import Base, users_schema

REASON_ANONYMIZATION = 'anonymization'
REASON_MERGE = 'merge'
REASON_SPAM = 'spam'
REASONS = [REASON_ANONYMIZATION, REASON_MERGE, REASON_SPAM]

STATUS_IN_PROGRESS = 'in_progress'
STATUS_VALIDATED = 'validated'
STATUS_DONE = 'done'

SIDE_TOPOGUIDE = 'topoguide'
SIDE_FORUM = 'forum'
SIDES = [SIDE_TOPOGUIDE, SIDE_FORUM]


class AccountRemovalRequest(Base):
    """A request to anonymize, merge or delete a user account.

    The request is made by a moderator, then validated by a moderator of the
    topoguide and by a moderator of the forum (three different persons). Once
    validated and past its date, the scripts/users/process_removals.py script
    merges the account into the target one.

    The users are kept as plain ids (no foreign key): the account is deleted by
    the merge, and the request remains as a trace of it.
    """

    __tablename__ = 'account_removal_request'
    __table_args__ = (
        # one open request by account
        Index(
            'account_removal_request_open_user_id_idx',
            'user_id',
            unique=True,
            postgresql_where=text('done_at IS NULL'),
        ),
        {'schema': users_schema},
    )

    id = Column(Integer, primary_key=True)

    # the account to remove: its ids in the topoguide and in the forum, and
    # its names, as the account does not exist anymore once done
    user_id = Column(Integer, nullable=False)
    forum_id = Column(Integer)
    user_name = Column(String(200), nullable=False)
    user_forum_username = Column(String(25), nullable=False)

    reason = Column(String(20), nullable=False)
    # the account can not be removed before this date
    executable_after = Column(Date, nullable=False)

    # the accounts to merge into
    target_user_id = Column(Integer, nullable=False)
    target_forum_id = Column(Integer, nullable=False)

    forum_url = Column(String(500))

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        server_default=func.now(),
    )
    requested_by = Column(Integer, nullable=False)

    topoguide_validated_by = Column(Integer)
    topoguide_validated_at = Column(DateTime(timezone=True))
    forum_validated_by = Column(Integer)
    forum_validated_at = Column(DateTime(timezone=True))

    done_at = Column(DateTime(timezone=True))

    @property
    def status(self):
        if self.done_at is not None:
            return STATUS_DONE
        if (
            self.topoguide_validated_by is not None
            and self.forum_validated_by is not None
        ):
            return STATUS_VALIDATED
        return STATUS_IN_PROGRESS
