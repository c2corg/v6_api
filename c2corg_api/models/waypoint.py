from typing import List, Optional

from sqlalchemy import Boolean, ForeignKey, Integer, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from c2corg_api.models import Base, enums, schema
from c2corg_api.models.common import document_types
from c2corg_api.models.document import (
    ArchiveDocument,
    ArchiveDocumentLocale,
    Document,
    DocumentLocale,
    geometry_attributes,
    schema_attributes,
    schema_locale_attributes,
)
from c2corg_api.models.field_spec import build_field_spec
from c2corg_api.models.utils import ArrayOfEnum, copy_attributes

WAYPOINT_TYPE = document_types.WAYPOINT_TYPE


class _WaypointMixin:
    # type de WP
    waypoint_type: Mapped[str] = mapped_column(enums.waypoint_type, nullable=False)

    # altitude
    elevation: Mapped[Optional[int]] = mapped_column(SmallInteger)

    # altitude min. (access)
    elevation_min: Mapped[Optional[int]] = mapped_column(SmallInteger)

    # proeminence/hauteur de culminance (summit)
    prominence: Mapped[Optional[int]] = mapped_column(SmallInteger)

    # hauteur max. (climbing_outdoor/indoor)
    height_max: Mapped[Optional[int]] = mapped_column(SmallInteger)

    # hauteur median (climbing_outdoor/indoor)
    height_median: Mapped[Optional[int]] = mapped_column(SmallInteger)

    # hauteur min (climbing_outdoor/indoor)
    height_min: Mapped[Optional[int]] = mapped_column(SmallInteger)

    # nombre de voies (climbing_outdoor/indoor)
    routes_quantity: Mapped[Optional[int]] = mapped_column(SmallInteger)

    # type de site (climbing_outdoor)
    climbing_outdoor_types: Mapped[Optional[List[str]]] = mapped_column(
        ArrayOfEnum(enums.climbing_outdoor_type)
    )

    # type de site (climbing_indoor)
    climbing_indoor_types: Mapped[Optional[List[str]]] = mapped_column(
        ArrayOfEnum(enums.climbing_indoor_type)
    )

    # cotation max (climbing_outdoor/indoor)
    climbing_rating_max: Mapped[Optional[str]] = mapped_column(enums.climbing_rating)

    # cotation min (climbing_outdoor/indoor)
    climbing_rating_min: Mapped[Optional[str]] = mapped_column(enums.climbing_rating)

    # cotation median (climbing_outdoor/indoor)
    climbing_rating_median: Mapped[Optional[str]] = mapped_column(enums.climbing_rating)

    # qualite de l'equipement (climbing_outdoor)
    equipment_ratings: Mapped[Optional[List[str]]] = mapped_column(
        ArrayOfEnum(enums.equipment_rating)
    )

    # styles d'escalade (climbing_outdoor/indoor)
    climbing_styles: Mapped[Optional[List[str]]] = mapped_column(
        ArrayOfEnum(enums.climbing_style)
    )

    # enfants (climbing_outdoor/indoor)
    children_proof: Mapped[Optional[str]] = mapped_column(enums.children_proof_type)

    # pluie (climbing_outdoor/indoor)
    rain_proof: Mapped[Optional[str]] = mapped_column(enums.rain_proof_type)

    # orientations (climbing_outdoor/indoor, paragliding_takeoff/landing)
    orientations: Mapped[Optional[List[str]]] = mapped_column(
        ArrayOfEnum(enums.orientation_type)
    )

    # meilleurs periodes (climbing_outdoor/indoor, paragliding_takeoff/landing)
    best_periods: Mapped[Optional[List[str]]] = mapped_column(
        ArrayOfEnum(enums.month_type)
    )

    # type de produits locaux (local_product)
    product_types: Mapped[Optional[List[str]]] = mapped_column(
        ArrayOfEnum(enums.product_type)
    )

    # longueur (lac, paragliding_takeoff/landing)
    length: Mapped[Optional[int]] = mapped_column(SmallInteger)

    # pente (paragliding_takeoff/landing)
    slope: Mapped[Optional[int]] = mapped_column(SmallInteger)

    # nature du sol (paragliding_takeoff/landing)
    ground_types: Mapped[Optional[List[str]]] = mapped_column(
        ArrayOfEnum(enums.ground_type)
    )

    # cotation deco/attero (paragliding_takeoff/landing)
    paragliding_rating: Mapped[Optional[str]] = mapped_column(enums.paragliding_rating)

    # exposition (paragliding_takeoff/landing)
    exposition_rating: Mapped[Optional[str]] = mapped_column(enums.exposition_rating)

    # type de rocher (summit, waterfall, cave, climbing_outdoor,
    # climbing_outdoor/indoor)
    rock_types: Mapped[Optional[List[str]]] = mapped_column(
        ArrayOfEnum(enums.rock_type)
    )

    # grandeurs mesurees (weatherstation)
    weather_station_types: Mapped[Optional[List[str]]] = mapped_column(
        ArrayOfEnum(enums.weather_station_type)
    )

    # url (climbing_outdoor/indoor, gite, camp_site, hut, base_camp,
    # local_product, sport_shop, paragliding_takeoff/landing, weather_station,
    # webcam)
    url: Mapped[Optional[str]] = mapped_column(String(255))

    # cartographie (all except bivouac, local_product, sport_shop,
    # paragliding_takeoff/landing, weather_station, webcam)
    maps_info: Mapped[Optional[str]] = mapped_column(String(300))

    # telephone (climbing_indoor, gite, camp_site, hut, local_product,
    # sport_shop)
    phone: Mapped[Optional[str]] = mapped_column(String(50))

    # type de transport en commun (access)
    public_transportation_types: Mapped[Optional[List[str]]] = mapped_column(
        ArrayOfEnum(enums.public_transportation_type)
    )

    # accessibilite en transports en commun (access)
    public_transportation_rating: Mapped[Optional[str]] = mapped_column(
        enums.public_transportation_rating
    )

    # deneigement (access)
    snow_clearance_rating: Mapped[Optional[str]] = mapped_column(
        enums.snow_clearance_rating
    )

    # servi par des remontees mecaniques (access)
    lift_access: Mapped[Optional[bool]] = mapped_column(Boolean)

    # parking payant (access)
    parking_fee: Mapped[Optional[str]] = mapped_column(enums.parking_fee_type)

    # telephone gardien/gerant (gite, camp_site, hut)
    phone_custodian: Mapped[Optional[str]] = mapped_column(String(50))

    # gardiennage (gite, camp_site, hut, abri, bivouac, base_camp)
    custodianship: Mapped[Optional[str]] = mapped_column(enums.custodianship_type)

    # matelas hors gardiennage (hut, abri, bivouac, base_camp)
    matress_unstaffed: Mapped[Optional[bool]] = mapped_column(Boolean)

    # couvertures hors gardiennage (hut, abri)
    blanket_unstaffed: Mapped[Optional[bool]] = mapped_column(Boolean)

    # cuisiniere / gaz hors gardiennage (hut, abri)
    gas_unstaffed: Mapped[Optional[bool]] = mapped_column(Boolean)

    # chauffage hors gardiennage (hut, abri)
    heating_unstaffed: Mapped[Optional[bool]] = mapped_column(Boolean)

    # duree de l'approche (climbing_outdoor)
    access_time: Mapped[Optional[str]] = mapped_column(enums.access_time_type)

    # nb places hors gardiennage
    # (gite, camping refuge, abri, bivouac, base_camp)
    capacity: Mapped[Optional[int]] = mapped_column(SmallInteger)

    # nb places en gardiennage (gite, camping refuge)
    capacity_staffed: Mapped[Optional[int]] = mapped_column(SmallInteger)

    slackline_types: Mapped[Optional[List[str]]] = mapped_column(
        ArrayOfEnum(enums.slackline_type)
    )

    slackline_length_min: Mapped[Optional[int]] = mapped_column(SmallInteger)

    slackline_length_max: Mapped[Optional[int]] = mapped_column(SmallInteger)


attributes = [
    'waypoint_type',
    'elevation',
    'prominence',
    'length',
    'height_median',
    'elevation_min',
    'routes_quantity',
    'capacity',
    'slope',
    'height_max',
    'capacity_staffed',
    'climbing_outdoor_types',
    'climbing_indoor_types',
    'public_transportation_types',
    'product_types',
    'ground_types',
    'weather_station_types',
    'rain_proof',
    'public_transportation_rating',
    'paragliding_rating',
    'children_proof',
    'snow_clearance_rating',
    'exposition_rating',
    'rock_types',
    'orientations',
    'best_periods',
    'url',
    'maps_info',
    'phone',
    'lift_access',
    'phone_custodian',
    'custodianship',
    'parking_fee',
    'matress_unstaffed',
    'blanket_unstaffed',
    'gas_unstaffed',
    'heating_unstaffed',
    'climbing_styles',
    'access_time',
    'climbing_rating_max',
    'climbing_rating_min',
    'climbing_rating_median',
    'height_min',
    'equipment_ratings',
    'slackline_types',
    'slackline_length_min',
    'slackline_length_max',
]


class Waypoint(_WaypointMixin, Document):
    """ """

    __tablename__ = 'waypoints'

    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(schema + '.documents.document_id'), primary_key=True
    )

    __mapper_args__ = {
        'polymorphic_identity': WAYPOINT_TYPE,
        'inherit_condition': Document.document_id == document_id,
    }

    def to_archive(self):
        waypoint = ArchiveWaypoint()
        super(Waypoint, self)._to_archive(waypoint)
        copy_attributes(self, waypoint, attributes)

        return waypoint

    def update(self, other):
        super(Waypoint, self).update(other)
        copy_attributes(other, self, attributes)

    def get_update_type(self, old_versions):
        update_types = super(Waypoint, self).get_update_type(old_versions)

        if self.public_transportation_rating != old_versions.get(
            'public_transportation_rating', None
        ):
            update_types[0].append('public_transportation_rating')

        return update_types


class ArchiveWaypoint(_WaypointMixin, ArchiveDocument):
    """ """

    __tablename__ = 'waypoints_archives'

    id: Mapped[int] = mapped_column(
        Integer, ForeignKey(schema + '.documents_archives.id'), primary_key=True
    )

    __mapper_args__ = {
        'polymorphic_identity': WAYPOINT_TYPE,
        'inherit_condition': ArchiveDocument.id == id,
    }

    __table_args__ = Base.__table_args__


class _WaypointLocaleMixin:
    # access (climbing_outdoor/indoor, access, local_product, sport_shop)
    access: Mapped[Optional[str]] = mapped_column(String)

    # field with multiple meanings:
    # restriction d'acces (climbing_outdoor)
    # horaires d'ouverture (climbing_indoor, local_product, sport_shop)
    # periode de gardiennage (gite, camp_site, hut)
    # date de deneigment ou d'ouverture (access)
    access_period: Mapped[Optional[str]] = mapped_column(String)

    # bibliographie et webographie
    external_resources: Mapped[Optional[str]] = mapped_column(String)


attributes_locales = ['access', 'access_period', 'external_resources']


class WaypointLocale(_WaypointLocaleMixin, DocumentLocale):
    """ """

    __tablename__ = 'waypoints_locales'

    id: Mapped[int] = mapped_column(
        Integer, ForeignKey(schema + '.documents_locales.id'), primary_key=True
    )

    __mapper_args__ = {
        'polymorphic_identity': WAYPOINT_TYPE,
        'inherit_condition': DocumentLocale.id == id,
    }

    def to_archive(self):
        locale = ArchiveWaypointLocale()
        super(WaypointLocale, self)._to_archive(locale)
        copy_attributes(self, locale, attributes_locales)

        return locale

    def update(self, other):
        super(WaypointLocale, self).update(other)
        copy_attributes(other, self, attributes_locales)


class ArchiveWaypointLocale(_WaypointLocaleMixin, ArchiveDocumentLocale):
    """ """

    __tablename__ = 'waypoints_locales_archives'

    id: Mapped[int] = mapped_column(
        Integer, ForeignKey(schema + '.documents_locales_archives.id'), primary_key=True
    )

    __mapper_args__ = {
        'polymorphic_identity': WAYPOINT_TYPE,
        'inherit_condition': ArchiveDocumentLocale.id == id,
    }

    __table_args__ = Base.__table_args__


schema_waypoint = build_field_spec(
    Waypoint,
    includes=schema_attributes + attributes,
    locale_fields=schema_locale_attributes + attributes_locales,
    geometry_fields=geometry_attributes,
)
