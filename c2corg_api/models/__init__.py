from sqlalchemy.ext.declarative import declarative_base

from sqlalchemy.orm import (
    scoped_session,
    sessionmaker,
    )

from zope.sqlalchemy import ZopeTransactionExtension

schema = 'guidebook'
users_schema = 'users'

DBSession = scoped_session(sessionmaker(extension=ZopeTransactionExtension()))


class BaseMixin(object):
    __table_args__ = {'schema': schema}

Base = declarative_base(cls=BaseMixin)


# all models, for which tables should be created, must be listed here:
from c2corg_api.models import document  # noqa
from c2corg_api.models import waypoint  # noqa
from c2corg_api.models import route  # noqa
from c2corg_api.models import document_history  # noqa
from c2corg_api.models import image  # noqa
from c2corg_api.models import user  # noqa
from c2corg_api.models import association  # noqa
from c2corg_api.models import topo_map  # noqa
from c2corg_api.models import area  # noqa
