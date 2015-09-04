from sqlalchemy import (
    Column,
    Integer,
    SmallInteger,
    String,
    ForeignKey,
    Enum
    )

from colanderalchemy import SQLAlchemySchemaNode

from . import schema
from document import (
    ArchiveDocument, Document, DocumentLocale, ArchiveDocumentLocale)

waypoint_types = [
    'summit',
    'pass',
    'lake',
    'bisse',
    'waterfall',
    'cave',
    'glacier',
    'cliff',
    'waterpoint',
    'canyon',
    'valley',
    'locality',
    'dam',
    'webcam',
    'weather_station',
    'hut',
    'gite',
    'shelter',
    'camp_site',
    'base_camp',
    'camping',
    'access',
    'crag',
    'boulder',
    'climbing',
    'local_product',
    'paragliding_takeoff',
    'paragliding_landing'
    ]


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


class ArchiveWaypoint(_WaypointMixin, ArchiveDocument):
    """
    """
    __tablename__ = 'waypoints_archives'

    id = Column(
        Integer,
        ForeignKey(schema + '.documents_archives.id'), primary_key=True)


class _WaypointLocaleMixin(object):
    waypoint_type = Column(
        Enum(name='waypoint_type', inherit_schema=True, *waypoint_types))

    pedestrian_access = Column(String)

    __mapper_args__ = {
        'polymorphic_identity': 'w'
    }


class WaypointLocale(_WaypointLocaleMixin, DocumentLocale):
    """
    """
    __tablename__ = 'waypoints_i18n'

    id = Column(
                Integer,
                ForeignKey(schema + '.documents_i18n.id'), primary_key=True)


class ArchiveWaypointLocale(_WaypointLocaleMixin, ArchiveDocumentLocale):
    """
    """
    __tablename__ = 'waypoints_i18n_archives'

    id = Column(
        Integer,
        ForeignKey(schema + '.documents_i18n_archives.id'), primary_key=True)


schema_waypoint_locale = SQLAlchemySchemaNode(
    WaypointLocale,
    # whitelisted attributes
    includes=['culture', 'title', 'description', 'pedestrian_access'])

schema_waypoint = SQLAlchemySchemaNode(
    Waypoint,
    # whitelisted attributes
    includes=[
        'document_id', 'waypoint_type', 'elevation', 'maps_info', 'locales'],
    overrides={
        'document_id': {
            'missing': None
        },
        'locales': {
            'children': [schema_waypoint_locale]
        }
    })
