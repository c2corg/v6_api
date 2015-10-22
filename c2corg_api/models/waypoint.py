from sqlalchemy import (
    Boolean,
    Column,
    Integer,
    SmallInteger,
    String,
    ForeignKey
    )

from colanderalchemy import SQLAlchemySchemaNode

from c2corg_api.models import schema
from utils import copy_attributes, ArrayOfEnum
from document import (
    ArchiveDocument, Document, DocumentLocale, ArchiveDocumentLocale,
    get_update_schema, geometry_schema_overrides)
from c2corg_api.models import enums


class _WaypointMixin(object):

    __mapper_args__ = {
        'polymorphic_identity': 'w'
    }

    # type de WP
    waypoint_type = Column(enums.waypoint_type, nullable=False)

    # altitude
    elevation = Column(SmallInteger)

    # proeminence/hauteur de culminance (summit)
    prominence = Column(SmallInteger)

    # longeur (lac, paragliding_takeoff/landing)
    length = Column(SmallInteger)

    # hauteur median (climbing_outdoor/indoor)
    height_median = Column(SmallInteger)

    # altitude min. (access)
    elevation_min = Column(SmallInteger)

    # nombre de voies (climbing_outdoor/indoor)
    routes_quantity = Column(SmallInteger)

    # nb places hors gardiennage
    # (gite, camping refuge, abri, bivouac, base_camp)
    capacity = Column(SmallInteger)

    # pente (lac, paragliding_takeoff/landing)
    slope = Column(SmallInteger)

    # hauteur max. (climbing_outdoor/indoor)
    height_max = Column(SmallInteger)

    # nb places en gardiennage (gite, camping refuge)
    capacity_staffed = Column(SmallInteger)

    # type de site (climbing_outdoor)
    climbing_outdoor_types = Column(ArrayOfEnum(enums.climbing_outdoor_type))

    # type de site (climbing_indoor)
    climbing_indoor_types = Column(ArrayOfEnum(enums.climbing_indoor_type))

    # type de transport en commun (access)
    public_transportation_types = Column(ArrayOfEnum(
        enums.public_transportation_type))

    # type de produits locaux (local_product)
    product_types = Column(ArrayOfEnum(enums.product_type))

    # type de produits locaux (paragliding_takeoff/landing)
    ground_types = Column(ArrayOfEnum(enums.ground_type))

    # type de produits locaux (paragliding_takeoff/landing)
    weather_station_types = Column(ArrayOfEnum(enums.weather_station_type))

    # pluie (climbing_outdoor/indoor)
    rain_proof = Column(enums.rain_proof_type)

    # accessibilite en transports en commun (access)
    public_transportation_rating = Column(enums.public_transportation_rating)

    # cotation deco/attero (paragliding_takeoff/landing)
    paragliding_rating = Column(enums.paragliding_rating)

    # enfants (climbing_outdoor/indoor)
    children_proof = Column(enums.children_proof_type)

    # deneigement (access)
    snow_clearance_rating = Column(enums.snow_clearance_rating)

    # exposition (paragliding_takeoff/landing)
    exposition_rating = Column(enums.exposition_rating)

    # activite (all types)
    activities = Column(ArrayOfEnum(enums.activity_type))

    # type de rocher (summit, waterfall, cave, pit, cliff,
    # climbing_outdoor/indoor)
    rock_types = Column(ArrayOfEnum(enums.rock_type))

    # orientation (climbing_outdoor/indoor, paragliding_takeoff/landing)
    orientation = Column(ArrayOfEnum(enums.orientation_type))

    # meilleurs periodes (climbing_outdoor/indoor, paragliding_takeoff/landing)
    best_periods = Column(ArrayOfEnum(enums.month_type))

    # url (climbing_outdoor/indoor, gite, camp_site, hut, base_camp,
    # local_product, sport_shop, paragliding_takeoff/landing, weather_station,
    # webcam)
    url = Column(String(255))

    # cartographie (all except bivouac, local_product, sport_shop,
    # paragliding_takeoff/landing, weather_station, webcam)
    maps_info = Column(String(300))

    # telephone (climbing_indoor, gite, camp_site, hut, local_product,
    # sport_shop)
    phone = Column(String(50))

    # servi par des remontees mecaniques (access)
    lift_access = Column(Boolean)

    # wc (base_camp, access)
    toilet = Column(Boolean)

    # telephone gardien/gerant (gite, camp_site, hut)
    phone_custodian = Column(String(50))

    # gardiennage (gite, camp_site, hut, abri, bivouac, base_camp)
    custodianship = Column(enums.custodianship_type)

    # parking payant (access)
    parking_fee = Column(enums.parking_fee_type)

    # matelas hors gardiennage (hut, abri, bivouac, base_camp)
    matress_unstaffed = Column(Boolean)

    # couvertures hors gardiennage (hut, abri)
    blanket_unstaffed = Column(Boolean)

    # cuisiniere / gaz hors gardiennage (hut, abri)
    gas_unstaffed = Column(Boolean)

    # chauffage hors gardiennage (hut, abri)
    heating_unstaffed = Column(Boolean)

    # styles d'escalade (climbing_outdoor/indoor)
    climbing_styles = Column(ArrayOfEnum(enums.climbing_style))

    # duree de l'approche (randkluft, cliff, climbing_outdoor)
    access_time = Column(enums.access_time_type)

    # cotation max (climbing_outdoor/indoor)
    climbing_rating_max = Column(enums.climbing_rating)

    # cotation min (climbing_outdoor/indoor)
    climbing_rating_min = Column(enums.climbing_rating)

    # cotation median (climbing_outdoor/indoor)
    climbing_rating_median = Column(enums.climbing_rating)

    # hauteur min (climbing_outdoor/indoor)
    height_min = Column(SmallInteger)

    # qualite de l'equipement (climbing_outdoor)
    equipment_ratings = Column(ArrayOfEnum(enums.equipment_rating))


attributes = [
    'waypoint_type', 'elevation', 'prominence', 'length', 'height_median',
    'elevation_min', 'routes_quantity', 'capacity', 'slope', 'height_max',
    'capacity_staffed', 'climbing_outdoor_types', 'climbing_indoor_types',
    'public_transportation_types', 'product_types', 'ground_types',
    'weather_station_types', 'rain_proof', 'public_transportation_rating',
    'paragliding_rating', 'children_proof', 'snow_clearance_rating',
    'exposition_rating', 'activities', 'rock_types', 'orientation',
    'best_periods', 'url', 'maps_info', 'phone', 'lift_access', 'toilet',
    'phone_custodian', 'custodianship', 'parking_fee', 'matress_unstaffed',
    'blanket_unstaffed', 'gas_unstaffed', 'heating_unstaffed',
    'climbing_styles', 'access_time', 'climbing_rating_max',
    'climbing_rating_min', 'climbing_rating_median', 'height_min',
    'equipment_ratings'
]


class Waypoint(_WaypointMixin, Document):
    """
    """
    __tablename__ = 'waypoints'

    document_id = Column(
        Integer,
        ForeignKey(schema + '.documents.document_id'), primary_key=True)

    def to_archive(self):
        waypoint = ArchiveWaypoint()
        super(Waypoint, self)._to_archive(waypoint)
        copy_attributes(self, waypoint, attributes)

        return waypoint

    def update(self, other):
        super(Waypoint, self).update(other)
        copy_attributes(other, self, attributes)


class ArchiveWaypoint(_WaypointMixin, ArchiveDocument):
    """
    """
    __tablename__ = 'waypoints_archives'

    id = Column(
        Integer,
        ForeignKey(schema + '.documents_archives.id'), primary_key=True)


class _WaypointLocaleMixin(object):
    __mapper_args__ = {
        'polymorphic_identity': 'w'
    }

    # resume (all)
    summary = Column(String(255))

    # access (climbing_outdoor/indoor, access, local_product, sport_shop)
    access = Column(String)

    # field with multiple meanings:
    # restriction d'acces (climbing_outdoor)
    # horaires d'ouverture (climbing_indoor, local_product, sport_shop)
    # periode de gardiennage (gite, camp_site, hut)
    # date de deneigment ou d'ouverture (access)
    access_period = Column(String)


attributes_locales = [
    'summary', 'access', 'access_period'
]


class WaypointLocale(_WaypointLocaleMixin, DocumentLocale):
    """
    """
    __tablename__ = 'waypoints_locales'

    id = Column(
                Integer,
                ForeignKey(schema + '.documents_locales.id'), primary_key=True)

    def to_archive(self):
        locale = ArchiveWaypointLocale()
        super(WaypointLocale, self).to_archive(locale)
        copy_attributes(self, locale, attributes_locales)

        return locale

    def update(self, other):
        super(WaypointLocale, self).update(other)
        copy_attributes(other, self, attributes_locales)


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
    includes=[
        'version', 'culture', 'title', 'description'] + attributes_locales,
    overrides={
        'version': {
            'missing': None
        }
    })


schema_waypoint = SQLAlchemySchemaNode(
    Waypoint,
    # whitelisted attributes
    includes=['document_id', 'version', 'locales', 'geometry'] + attributes,
    overrides={
        'document_id': {
            'missing': None
        },
        'version': {
            'missing': None
        },
        'locales': {
            'children': [schema_waypoint_locale]
        },
        'geometry': geometry_schema_overrides
    })

schema_update_waypoint = get_update_schema(schema_waypoint)
