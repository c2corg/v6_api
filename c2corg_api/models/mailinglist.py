from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql.functions import func

from c2corg_api.models import Base, sympa_schema, users_schema
from c2corg_api.models.user import User


class Mailinglist(Base):
    """
    Class containing mailing list subscriptions.
    Based upon Sympa mailing list server https://www.sympa.org/
    """
    __tablename__ = 'subscriber_table'
    __table_args__ = {"schema": sympa_schema}

    listname = Column('list_subscriber', String(50), primary_key=True)
    email = Column('user_subscriber', String(200), primary_key=True)
    user_id = Column(
        Integer, ForeignKey(users_schema + '.user.id'), nullable=False)
    user = relationship(User, primaryjoin=user_id == User.id)

    # additional fields, used only by Sympa
    date_subscriber = Column(
        DateTime, default=func.now(), server_default=func.now(),
        nullable=False)
    update_subscriber = Column(DateTime)
    visibility_subscriber = Column(String(20))
    reception_subscriber = Column(String(20))
    bounce_subscriber = Column(String(35))
    bounce_score_subscriber = Column(Integer)
    comment_subscriber = Column(String(150))
    subscribed_subscriber = Column(Integer)
    included_subscriber = Column(Integer)
    include_sources_subscriber = Column(String(50))
