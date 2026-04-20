from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from c2corg_api.models import Base, sympa_schema, users_schema
from c2corg_api.models.user import User


class Mailinglist(Base):
    """
    Class containing mailing list subscriptions.
    Based upon Sympa mailing list server https://www.sympa.org/
    """

    __tablename__ = 'subscriber_table'
    __table_args__ = {'schema': sympa_schema}

    listname: Mapped[str] = mapped_column(
        'list_subscriber', String(50), primary_key=True
    )
    email: Mapped[str] = mapped_column('user_subscriber', String(200), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(users_schema + '.user.id'), nullable=False
    )
    user = relationship(User, primaryjoin=user_id == User.id)

    # additional fields, used only by Sympa
    date_subscriber: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), server_default=func.now(), nullable=False
    )
    update_subscriber: Mapped[Optional[datetime]] = mapped_column(DateTime)
    visibility_subscriber: Mapped[Optional[str]] = mapped_column(String(20))
    reception_subscriber: Mapped[Optional[str]] = mapped_column(String(20))
    bounce_subscriber: Mapped[Optional[str]] = mapped_column(String(35))
    bounce_score_subscriber: Mapped[Optional[int]] = mapped_column(Integer)
    comment_subscriber: Mapped[Optional[str]] = mapped_column(String(150))
    subscribed_subscriber: Mapped[Optional[int]] = mapped_column(Integer)
    included_subscriber: Mapped[Optional[int]] = mapped_column(Integer)
    include_sources_subscriber: Mapped[Optional[str]] = mapped_column(String(50))
