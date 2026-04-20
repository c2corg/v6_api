from typing import List, Optional

from sqlalchemy import Boolean, Float, ForeignKey, Integer, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

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

ROUTE_TYPE = document_types.ROUTE_TYPE


class _RouteMixin:
    # activite
    activities: Mapped[List[str]] = mapped_column(
        ArrayOfEnum(enums.activity_type), nullable=False
    )

    # altitude min.
    elevation_min: Mapped[Optional[int]] = mapped_column(SmallInteger)

    # altitude max.
    elevation_max: Mapped[Optional[int]] = mapped_column(SmallInteger)

    # denivele positif du troncon dans le sens aller
    height_diff_up: Mapped[Optional[int]] = mapped_column(SmallInteger)

    # denivele negatif du troncon dans le sens aller
    height_diff_down: Mapped[Optional[int]] = mapped_column(SmallInteger)

    # longueur du troncon
    route_length: Mapped[Optional[int]] = mapped_column(Integer)

    # altitude du debut des difficultes
    difficulties_height: Mapped[Optional[int]] = mapped_column(SmallInteger)

    # denivele de l'approche
    height_diff_access: Mapped[Optional[int]] = mapped_column(SmallInteger)

    # Denivele des difficultes
    height_diff_difficulties: Mapped[Optional[int]] = mapped_column(SmallInteger)

    # type d'itineraire (aller-retour, boucle, ...)
    route_types: Mapped[Optional[List[str]]] = mapped_column(
        ArrayOfEnum(enums.route_type)
    )

    # orientations
    orientations: Mapped[Optional[List[str]]] = mapped_column(
        ArrayOfEnum(enums.orientation_type)
    )

    # temps de parcours total, renseigné par l'utilisateur
    durations: Mapped[Optional[List[str]]] = mapped_column(
        ArrayOfEnum(enums.route_duration_type)
    )

    # temps de parcours total estimé, calculé
    calculated_duration: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # crampons et materiel de securite sur glacier
    glacier_gear: Mapped[str] = mapped_column(
        enums.glacier_gear_type, default='no', server_default='no', nullable=False
    )

    # configuration
    configuration: Mapped[Optional[List[str]]] = mapped_column(
        ArrayOfEnum(enums.route_configuration_type)
    )

    # approche par remontee mecanique possible
    lift_access: Mapped[Optional[bool]] = mapped_column(Boolean)

    # cotation technique ski
    ski_rating: Mapped[Optional[str]] = mapped_column(enums.ski_rating)

    # exposition ski
    ski_exposition: Mapped[Optional[str]] = mapped_column(enums.exposition_rating)

    # cotation ponctuelle ski
    labande_ski_rating: Mapped[Optional[str]] = mapped_column(enums.labande_ski_rating)

    # cotation globale ski
    labande_global_rating: Mapped[Optional[str]] = mapped_column(enums.global_rating)

    # cotation globale
    global_rating: Mapped[Optional[str]] = mapped_column(enums.global_rating)

    # engagement
    engagement_rating: Mapped[Optional[str]] = mapped_column(enums.engagement_rating)

    # risques objectifs
    risk_rating: Mapped[Optional[str]] = mapped_column(enums.risk_rating)

    # qualite de l'equipement en place
    equipment_rating: Mapped[Optional[str]] = mapped_column(enums.equipment_rating)

    # cotation glace
    ice_rating: Mapped[Optional[str]] = mapped_column(enums.ice_rating)

    # cotation mixte
    mixed_rating: Mapped[Optional[str]] = mapped_column(enums.mixed_rating)

    # exposition rocher
    exposition_rock_rating: Mapped[Optional[str]] = mapped_column(
        enums.exposition_rock_rating
    )

    # cotation libre FR
    rock_free_rating: Mapped[Optional[str]] = mapped_column(enums.climbing_rating)

    # cotation obligatoire FR
    rock_required_rating: Mapped[Optional[str]] = mapped_column(enums.climbing_rating)

    # cotation escalade artificielle obligatoire
    aid_rating: Mapped[Optional[str]] = mapped_column(enums.aid_rating)

    # cotation via ferrata
    via_ferrata_rating: Mapped[Optional[str]] = mapped_column(enums.via_ferrata_rating)

    # cotation randonee
    hiking_rating: Mapped[Optional[str]] = mapped_column(enums.hiking_rating)

    # Exposition randonnee et VTT
    hiking_mtb_exposition: Mapped[Optional[str]] = mapped_column(
        enums.exposition_rating
    )

    # cotation raquette
    snowshoe_rating: Mapped[Optional[str]] = mapped_column(enums.snowshoe_rating)

    # cotation VTT (montee)
    mtb_up_rating: Mapped[Optional[str]] = mapped_column(enums.mtb_up_rating)

    # cotation VTT (descente)
    mtb_down_rating: Mapped[Optional[str]] = mapped_column(enums.mtb_down_rating)

    # longueur de bitume
    mtb_length_asphalt: Mapped[Optional[int]] = mapped_column(Integer)

    # longueur de piste
    mtb_length_trail: Mapped[Optional[int]] = mapped_column(Integer)

    # denivele de portage ou poussage
    mtb_height_diff_portages: Mapped[Optional[int]] = mapped_column(Integer)

    # type de rocher
    rock_types: Mapped[Optional[List[str]]] = mapped_column(
        ArrayOfEnum(enums.rock_type)
    )

    # type de voie
    climbing_outdoor_type: Mapped[Optional[str]] = mapped_column(
        enums.climbing_outdoor_type
    )

    slackline_type: Mapped[Optional[str]] = mapped_column(enums.slackline_type)

    slackline_height: Mapped[Optional[int]] = mapped_column(SmallInteger)

    public_transportation_rating: Mapped[Optional[str]] = mapped_column(
        enums.public_transportation_rating
    )


attributes = [
    'main_waypoint_id',
    'activities',
    'elevation_min',
    'elevation_max',
    'height_diff_up',
    'height_diff_down',
    'route_length',
    'durations',
    'calculated_duration',
    'difficulties_height',
    'height_diff_access',
    'height_diff_difficulties',
    'route_types',
    'orientations',
    'glacier_gear',
    'configuration',
    'lift_access',
    'ski_rating',
    'ski_exposition',
    'labande_ski_rating',
    'labande_global_rating',
    'global_rating',
    'engagement_rating',
    'risk_rating',
    'equipment_rating',
    'ice_rating',
    'mixed_rating',
    'exposition_rock_rating',
    'rock_free_rating',
    'rock_required_rating',
    'aid_rating',
    'via_ferrata_rating',
    'hiking_rating',
    'hiking_mtb_exposition',
    'snowshoe_rating',
    'mtb_up_rating',
    'mtb_down_rating',
    'mtb_length_asphalt',
    'mtb_length_trail',
    'mtb_height_diff_portages',
    'rock_types',
    'climbing_outdoor_type',
    'slackline_type',
    'slackline_height',
    'public_transportation_rating',
]


class Route(_RouteMixin, Document):
    """ """

    __tablename__ = 'routes'

    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(schema + '.documents.document_id'), primary_key=True
    )

    main_waypoint_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey(schema + '.documents.document_id'),
        nullable=True,
        index=True,
    )
    main_waypoint = relationship(
        Document, primaryjoin=main_waypoint_id == Document.document_id
    )

    __mapper_args__ = {
        'polymorphic_identity': ROUTE_TYPE,
        'inherit_condition': Document.document_id == document_id,
    }

    def to_archive(self):
        route = ArchiveRoute()
        super(Route, self)._to_archive(route)
        copy_attributes(self, route, attributes)

        return route

    def update(self, other):
        super(Route, self).update(other)
        copy_attributes(other, self, attributes)


class ArchiveRoute(_RouteMixin, ArchiveDocument):
    """ """

    __tablename__ = 'routes_archives'

    id: Mapped[int] = mapped_column(
        Integer, ForeignKey(schema + '.documents_archives.id'), primary_key=True
    )

    main_waypoint_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey(schema + '.documents.document_id'), nullable=True
    )
    main_waypoint = relationship(
        Document, primaryjoin=main_waypoint_id == Document.document_id
    )

    __mapper_args__ = {
        'polymorphic_identity': ROUTE_TYPE,
        'inherit_condition': ArchiveDocument.id == id,
    }

    __table_args__ = Base.__table_args__


class _RouteLocaleMixin:
    # pente
    slope: Mapped[Optional[str]] = mapped_column(String)

    # remarques
    remarks: Mapped[Optional[str]] = mapped_column(String)

    # materiel specifique
    gear: Mapped[Optional[str]] = mapped_column(String)

    # bibliographie et webographie
    external_resources: Mapped[Optional[str]] = mapped_column(String)

    # historique de l'itineraire
    route_history: Mapped[Optional[str]] = mapped_column(String)

    slackline_anchor1: Mapped[Optional[str]] = mapped_column(String)

    slackline_anchor2: Mapped[Optional[str]] = mapped_column(String)


attributes_locales = [
    'slope',
    'remarks',
    'gear',
    'external_resources',
    'route_history',
    'slackline_anchor1',
    'slackline_anchor2',
]


class RouteLocale(_RouteLocaleMixin, DocumentLocale):
    """ """

    __tablename__ = 'routes_locales'

    id: Mapped[int] = mapped_column(
        Integer, ForeignKey(schema + '.documents_locales.id'), primary_key=True
    )

    __mapper_args__ = {
        'polymorphic_identity': ROUTE_TYPE,
        'inherit_condition': DocumentLocale.id == id,
    }

    # the cached title of the main waypoint
    title_prefix: Mapped[Optional[str]] = mapped_column(String)

    def to_archive(self):
        locale = ArchiveRouteLocale()
        super(RouteLocale, self)._to_archive(locale)
        copy_attributes(self, locale, attributes_locales)

        return locale

    def update(self, other):
        super(RouteLocale, self).update(other)
        copy_attributes(other, self, attributes_locales)


class ArchiveRouteLocale(_RouteLocaleMixin, ArchiveDocumentLocale):
    """ """

    __tablename__ = 'routes_locales_archives'

    id: Mapped[int] = mapped_column(
        Integer, ForeignKey(schema + '.documents_locales_archives.id'), primary_key=True
    )

    __mapper_args__ = {
        'polymorphic_identity': ROUTE_TYPE,
        'inherit_condition': ArchiveDocumentLocale.id == id,
    }

    __table_args__ = Base.__table_args__


schema_route = build_field_spec(
    Route,
    includes=schema_attributes + attributes,
    locale_fields=(schema_locale_attributes + attributes_locales + ['title_prefix']),
    geometry_fields=geometry_attributes,
)
