from sqlalchemy.ext.declarative import declarative_base

from sqlalchemy.orm import (
    scoped_session,
    sessionmaker,
    )

from zope.sqlalchemy import ZopeTransactionExtension

schema = 'topoguide'

DBSession = scoped_session(sessionmaker(extension=ZopeTransactionExtension()))


class BaseMixin(object):
    __table_args__ = {'schema': schema}

Base = declarative_base(cls=BaseMixin)


# all models, for which tables should be created, must be listed here:
from app_api.models import document  # noqa
from app_api.models import waypoint  # noqa
from app_api.models import document_history  # noqa
