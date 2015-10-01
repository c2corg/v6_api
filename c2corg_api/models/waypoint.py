from sqlalchemy import (
    Column,
    Integer,
    SmallInteger,
    String,
    ForeignKey,
    Enum
    )

from colanderalchemy import SQLAlchemySchemaNode

from c2corg_api.models import schema
from utils import copy_attributes
from document import (
    ArchiveDocument, Document, DocumentLocale, ArchiveDocumentLocale,
    get_update_schema)
from c2corg_api.attributes import waypoint_types


class _WaypointMixin(object):
    waypoint_type = Column(
        Enum(name='waypoint_type', inherit_schema=True, *waypoint_types),
        nullable=False)

    elevation = Column(SmallInteger)
    maps_info = Column(String(300))

    __mapper_args__ = {
        'polymorphic_identity': 'w'
    }


class Waypoint(_WaypointMixin, Document):
    """
    """
    __tablename__ = 'waypoints'

    document_id = Column(
        Integer,
        ForeignKey(schema + '.documents.document_id'), primary_key=True)

    _ATTRIBUTES = ['waypoint_type', 'elevation', 'maps_info']

    def to_archive(self):
        waypoint = ArchiveWaypoint()
        super(Waypoint, self)._to_archive(waypoint)
        copy_attributes(self, waypoint, Waypoint._ATTRIBUTES)

        return waypoint

    def update(self, other):
        super(Waypoint, self).update(other)
        copy_attributes(other, self, Waypoint._ATTRIBUTES)


class ArchiveWaypoint(_WaypointMixin, ArchiveDocument):
    """
    """
    __tablename__ = 'waypoints_archives'

    id = Column(
        Integer,
        ForeignKey(schema + '.documents_archives.id'), primary_key=True)


class _WaypointLocaleMixin(object):
    pedestrian_access = Column(String)

    __mapper_args__ = {
        'polymorphic_identity': 'w'
    }


class WaypointLocale(_WaypointLocaleMixin, DocumentLocale):
    """
    """
    __tablename__ = 'waypoints_locales'

    id = Column(
                Integer,
                ForeignKey(schema + '.documents_locales.id'), primary_key=True)

    _ATTRIBUTES = ['pedestrian_access']

    def to_archive(self):
        locale = ArchiveWaypointLocale()
        super(WaypointLocale, self).to_archive(locale)
        copy_attributes(self, locale, WaypointLocale._ATTRIBUTES)

        return locale

    def update(self, other):
        super(WaypointLocale, self).update(other)
        copy_attributes(other, self, WaypointLocale._ATTRIBUTES)


class ArchiveWaypointLocale(_WaypointLocaleMixin, ArchiveDocumentLocale):
    """
    """
    __tablename__ = 'waypoints_locales_archives'

    id = Column(
        Integer,
        ForeignKey(schema + '.documents_locales_archives.id'),
        primary_key=True)


schema_waypoint_locale = SQLAlchemySchemaNode(
    WaypointLocale,
    # whitelisted attributes
    includes=['version', 'culture', 'title', 'description',
              'pedestrian_access'],
    overrides={
        'version': {
            'missing': None
        }
    })

schema_waypoint = SQLAlchemySchemaNode(
    Waypoint,
    # whitelisted attributes
    includes=[
        'document_id', 'version', 'waypoint_type', 'elevation', 'maps_info',
        'locales'],
    overrides={
        'document_id': {
            'missing': None
        },
        'version': {
            'missing': None
        },
        'locales': {
            'children': [schema_waypoint_locale]
        }
    })

schema_update_waypoint = get_update_schema(schema_waypoint)
