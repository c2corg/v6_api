from c2corg_api.models.field_spec import build_field_spec
from sqlalchemy import (
    Column,
    Integer,
    Float,
    Boolean,
    SmallInteger,
    String,
    ForeignKey
)

from c2corg_api.models import schema, Base
from c2corg_api.models.utils import ArrayOfEnum
from c2corg_api.models.utils import copy_attributes
from c2corg_api.models.document import (
    ArchiveDocument, Document, DocumentLocale, ArchiveDocumentLocale,
    schema_locale_attributes, schema_attributes, geometry_attributes)
from c2corg_api.models import enums
from sqlalchemy.orm import relationship
from c2corg_api.models.common import document_types

ROUTE_TYPE = document_types.ROUTE_TYPE


class _RouteMixin(object):

    # activite
    activities = Column(ArrayOfEnum(enums.activity_type), nullable=False)

    # altitude min.
    elevation_min = Column(SmallInteger)

    # altitude max.
    elevation_max = Column(SmallInteger)

    # denivele positif du troncon dans le sens aller
    height_diff_up = Column(SmallInteger)

    # denivele negatif du troncon dans le sens aller
    height_diff_down = Column(SmallInteger)

    # longueur du troncon
    route_length = Column(Integer)

    # altitude du debut des difficultes
    difficulties_height = Column(SmallInteger)

    # denivele de l'approche
    height_diff_access = Column(SmallInteger)

    # Denivele des difficultes
    height_diff_difficulties = Column(SmallInteger)

    # type d'itineraire (aller-retour, boucle, ...)
    route_types = Column(ArrayOfEnum(enums.route_type))

    # orientations
    orientations = Column(ArrayOfEnum(enums.orientation_type))

    # temps de parcours total, renseigné par l'utilisateur
    durations = Column(ArrayOfEnum(enums.route_duration_type))

    # temps de parcours total estimé, calculé
    calculated_duration = Column(Float, nullable=True)

    # crampons et materiel de securite sur glacier
    glacier_gear = Column(
        enums.glacier_gear_type, default='no', server_default='no',
        nullable=False)

    # configuration
    configuration = Column(ArrayOfEnum(enums.route_configuration_type))

    # approche par remontee mecanique possible
    lift_access = Column(Boolean)

    # cotation technique ski
    ski_rating = Column(enums.ski_rating)

    # exposition ski
    ski_exposition = Column(enums.exposition_rating)

    # cotation ponctuelle ski
    labande_ski_rating = Column(enums.labande_ski_rating)

    # cotation globale ski
    labande_global_rating = Column(enums.global_rating)

    # cotation globale
    global_rating = Column(enums.global_rating)

    # engagement
    engagement_rating = Column(enums.engagement_rating)

    # risques objectifs
    risk_rating = Column(enums.risk_rating)

    # qualite de l'equipement en place
    equipment_rating = Column(enums.equipment_rating)

    # cotation glace
    ice_rating = Column(enums.ice_rating)

    # cotation mixte
    mixed_rating = Column(enums.mixed_rating)

    # exposition rocher
    exposition_rock_rating = Column(enums.exposition_rock_rating)

    # cotation libre FR
    rock_free_rating = Column(enums.climbing_rating)

    # cotation obligatoire FR
    rock_required_rating = Column(enums.climbing_rating)

    # cotation escalade artificielle obligatoire
    aid_rating = Column(enums.aid_rating)

    # cotation via ferrata
    via_ferrata_rating = Column(enums.via_ferrata_rating)

    # cotation randonee
    hiking_rating = Column(enums.hiking_rating)

    # Exposition randonnee et VTT
    hiking_mtb_exposition = Column(enums.exposition_rating)

    # cotation raquette
    snowshoe_rating = Column(enums.snowshoe_rating)

    # cotation VTT (montee)
    mtb_up_rating = Column(enums.mtb_up_rating)

    # cotation VTT (descente)
    mtb_down_rating = Column(enums.mtb_down_rating)

    # longueur de bitume
    mtb_length_asphalt = Column(Integer)

    # longueur de piste
    mtb_length_trail = Column(Integer)

    # denivele de portage ou poussage
    mtb_height_diff_portages = Column(Integer)

    # type de rocher
    rock_types = Column(ArrayOfEnum(enums.rock_type))

    # type de voie
    climbing_outdoor_type = Column(enums.climbing_outdoor_type)

    slackline_type = Column(enums.slackline_type)

    slackline_height = Column(SmallInteger)

    public_transportation_rating = Column(enums.public_transportation_rating)


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
    'public_transportation_rating']


class Route(_RouteMixin, Document):
    """
    """
    __tablename__ = 'routes'

    document_id = Column(
        Integer,
        ForeignKey(schema + '.documents.document_id'), primary_key=True)

    main_waypoint_id = Column(
        Integer, ForeignKey(schema + '.documents.document_id'), nullable=True,
        index=True)
    main_waypoint = relationship(
        Document, primaryjoin=main_waypoint_id == Document.document_id)

    __mapper_args__ = {
        'polymorphic_identity': ROUTE_TYPE,
        'inherit_condition': Document.document_id == document_id
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
    """
    """
    __tablename__ = 'routes_archives'

    id = Column(
        Integer,
        ForeignKey(schema + '.documents_archives.id'), primary_key=True)

    main_waypoint_id = Column(
        Integer, ForeignKey(schema + '.documents.document_id'), nullable=True)
    main_waypoint = relationship(
        Document, primaryjoin=main_waypoint_id == Document.document_id)

    __mapper_args__ = {
        'polymorphic_identity': ROUTE_TYPE,
        'inherit_condition': ArchiveDocument.id == id
    }

    __table_args__ = Base.__table_args__


class _RouteLocaleMixin(object):

    # pente
    slope = Column(String)

    # remarques
    remarks = Column(String)

    # materiel specifique
    gear = Column(String)

    # bibliographie et webographie
    external_resources = Column(String)

    # historique de l'itineraire
    route_history = Column(String)

    slackline_anchor1 = Column(String)

    slackline_anchor2 = Column(String)


attributes_locales = [
    'slope', 'remarks', 'gear', 'external_resources', 'route_history',
    'slackline_anchor1', 'slackline_anchor2'
]


class RouteLocale(_RouteLocaleMixin, DocumentLocale):
    """
    """
    __tablename__ = 'routes_locales'

    id = Column(
        Integer,
        ForeignKey(schema + '.documents_locales.id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': ROUTE_TYPE,
        'inherit_condition': DocumentLocale.id == id
    }

    # the cached title of the main waypoint
    title_prefix = Column(String)

    def to_archive(self):
        locale = ArchiveRouteLocale()
        super(RouteLocale, self)._to_archive(locale)
        copy_attributes(self, locale, attributes_locales)

        return locale

    def update(self, other):
        super(RouteLocale, self).update(other)
        copy_attributes(other, self, attributes_locales)


class ArchiveRouteLocale(_RouteLocaleMixin, ArchiveDocumentLocale):
    """
    """
    __tablename__ = 'routes_locales_archives'

    id = Column(
        Integer,
        ForeignKey(schema + '.documents_locales_archives.id'),
        primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': ROUTE_TYPE,
        'inherit_condition': ArchiveDocumentLocale.id == id
    }

    __table_args__ = Base.__table_args__


schema_route = build_field_spec(
    Route,
    includes=schema_attributes + attributes,
    locale_fields=(
        schema_locale_attributes + attributes_locales + ['title_prefix']
    ),
    geometry_fields=geometry_attributes,
)


# ===================================================================
# Pydantic schemas (generated from the SQLAlchemy model)
# ===================================================================
from c2corg_api.models.pydantic import (  # noqa: E402
    schema_from_sa_model,
    get_update_schema as pydantic_update_schema,
    get_create_schema as pydantic_create_schema,
    DocumentGeometrySchema,
    AssociationsSchema,
    LangType,
    _DuplicateLocalesMixin,
)
from typing import List, Optional  # noqa: E402

# -- route locale schema (extends DocumentLocaleSchema with route fields) ---

_RouteLocaleBase = schema_from_sa_model(
    RouteLocale,
    name='_RouteLocaleBase',
    includes=schema_locale_attributes + attributes_locales + ['title_prefix'],
    overrides={
        'version': {'default': None},
        'lang': {'type': LangType},
    },
)


class RouteLocaleSchema(_RouteLocaleBase):
    """Locale for route create/update requests."""
    model_config = {"extra": "ignore"}


# -- route document schema --------------------------------------------------

_route_schema_attrs = [
    a for a in schema_attributes + attributes
    if a not in ('locales', 'geometry')
]

_RouteDocBase = schema_from_sa_model(
    Route,
    name='_RouteDocBase',
    includes=_route_schema_attrs,
    overrides={
        'document_id': {'default': None},
        'version': {'default': None},
        # Accept any string for activities; downstream validators
        # (validate_document_for_type) check valid values.
        'activities': {'type': List[str]},
    },
)


class RouteDocumentSchema(
    _DuplicateLocalesMixin, _RouteDocBase,
):
    """Full route document for create/update requests."""
    locales: Optional[List[RouteLocaleSchema]] = None
    geometry: Optional[DocumentGeometrySchema] = None
    associations: Optional[AssociationsSchema] = None
    model_config = {"extra": "ignore"}


# -- create / update envelopes -----------------------------------------------

CreateRouteSchema = pydantic_create_schema(
    RouteDocumentSchema,
    name='CreateRouteSchema',
)

UpdateRouteSchema = pydantic_update_schema(
    RouteDocumentSchema,
    name='UpdateRouteSchema',
)
