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
from c2corg_api.models import area_association  # noqa
from c2corg_api.models import topo_map_association  # noqa
from c2corg_api.models import user_profile  # noqa
from c2corg_api.models import outing  # noqa
from c2corg_api.models import es_sync  # noqa
from c2corg_api.models import association_views  # noqa
from c2corg_api.models import cache_version  # noqa

document_types = {
    waypoint.WAYPOINT_TYPE: waypoint.Waypoint,
    route.ROUTE_TYPE: route.Route,
    image.IMAGE_TYPE: image.Image,
    user_profile.USERPROFILE_TYPE: user_profile.UserProfile,
    topo_map.MAP_TYPE: topo_map.TopoMap,
    area.AREA_TYPE: area.Area,
    outing.OUTING_TYPE: outing.Outing
}

document_locale_types = {
    waypoint.WAYPOINT_TYPE: waypoint.WaypointLocale,
    route.ROUTE_TYPE: route.RouteLocale,
    image.IMAGE_TYPE: document.DocumentLocale,
    user_profile.USERPROFILE_TYPE: document.DocumentLocale,
    topo_map.MAP_TYPE: document.DocumentLocale,
    area.AREA_TYPE: document.DocumentLocale,
    outing.OUTING_TYPE: outing.OutingLocale
}
