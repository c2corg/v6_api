import colander
from c2corg_api.models.schema_utils import restrict_schema, \
    get_update_schema, get_create_schema
from sqlalchemy import (
    Column,
    Integer,
    Boolean,
    SmallInteger,
    String,
    Date,
    ForeignKey
    )

from colanderalchemy import SQLAlchemySchemaNode

from c2corg_api.models import schema, Base
from c2corg_api.models.utils import ArrayOfEnum
from c2corg_api.models.utils import copy_attributes
from c2corg_api.models.document import (
    ArchiveDocument, Document, DocumentLocale, ArchiveDocumentLocale,
    schema_locale_attributes,
    schema_attributes, get_geometry_schema_overrides)
from c2corg_api.models import enums
from c2corg_api.models.common import document_types

OUTING_TYPE = document_types.OUTING_TYPE


class _OutingMixin(object):

    activities = Column(ArrayOfEnum(enums.activity_type), nullable=False)

    date_start = Column(Date, nullable=False)

    date_end = Column(Date, nullable=False)

    frequentation = Column(enums.frequentation_type)

    participant_count = Column(SmallInteger)

    elevation_min = Column(SmallInteger)

    elevation_max = Column(SmallInteger)

    elevation_access = Column(SmallInteger)

    # altitude de chaussage
    elevation_up_snow = Column(SmallInteger)

    # altitude de dechaussage
    elevation_down_snow = Column(SmallInteger)

    height_diff_up = Column(SmallInteger)

    height_diff_down = Column(SmallInteger)

    length_total = Column(Integer)

    partial_trip = Column(Boolean)

    public_transport = Column(Boolean)

    access_condition = Column(enums.access_condition)

    lift_status = Column(enums.lift_status)

    condition_rating = Column(enums.condition_rating)

    snow_quantity = Column(enums.snow_quantity_ratings)

    snow_quality = Column(enums.snow_quality_ratings)

    glacier_rating = Column(enums.glacier_rating)

    avalanche_signs = Column(ArrayOfEnum(enums.avalanche_signs))

    hut_status = Column(enums.hut_status)

    disable_comments = Column(Boolean)

    hiking_rating = Column(enums.hiking_rating)

    ski_rating = Column(enums.ski_rating)

    labande_global_rating = Column(enums.global_rating)

    snowshoe_rating = Column(enums.snowshoe_rating)

    global_rating = Column(enums.global_rating)

    height_diff_difficulties = Column(SmallInteger)

    engagement_rating = Column(enums.engagement_rating)

    equipment_rating = Column(enums.equipment_rating)

    rock_free_rating = Column(enums.climbing_rating)

    ice_rating = Column(enums.ice_rating)

    via_ferrata_rating = Column(enums.via_ferrata_rating)

    mtb_up_rating = Column(enums.mtb_up_rating)

    mtb_down_rating = Column(enums.mtb_down_rating)


attributes = [
    'access_condition', 'activities', 'avalanche_signs',
    'condition_rating', 'date_end', 'date_start',
    'elevation_access', 'elevation_down_snow',
    'elevation_max', 'elevation_min', 'elevation_up_snow', 'frequentation',
    'glacier_rating', 'height_diff_down', 'height_diff_up', 'hut_status',
    'length_total', 'lift_status', 'partial_trip', 'participant_count',
    'public_transport', 'snow_quality', 'snow_quantity', 'disable_comments',
    'hiking_rating', 'ski_rating', 'labande_global_rating', 'ice_rating',
    'snowshoe_rating', 'global_rating', 'height_diff_difficulties',
    'engagement_rating', 'equipment_rating', 'rock_free_rating',
    'via_ferrata_rating', 'mtb_up_rating', 'mtb_down_rating'
    ]


class Outing(_OutingMixin, Document):
    """
    """
    __tablename__ = 'outings'

    document_id = Column(
        Integer,
        ForeignKey(schema + '.documents.document_id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': OUTING_TYPE,
        'inherit_condition': Document.document_id == document_id
    }

    def to_archive(self):
        outing = ArchiveOuting()
        super(Outing, self)._to_archive(outing)
        copy_attributes(self, outing, attributes)

        return outing

    def update(self, other):
        super(Outing, self).update(other)
        copy_attributes(other, self, attributes)


class ArchiveOuting(_OutingMixin, ArchiveDocument):
    """
    """
    __tablename__ = 'outings_archives'

    id = Column(
        Integer,
        ForeignKey(schema + '.documents_archives.id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': OUTING_TYPE,
        'inherit_condition': ArchiveDocument.id == id
    }

    __table_args__ = Base.__table_args__


class _OutingLocaleMixin(object):

    __mapper_args__ = {
        'polymorphic_identity': OUTING_TYPE
    }

    participants = Column(String)

    access_comment = Column(String)

    weather = Column(String)

    timing = Column(String)

    conditions_levels = Column(String)

    conditions = Column(String)

    avalanches = Column(String)

    hut_comment = Column(String)

    route_description = Column(String)


attributes_locales = [
    'access_comment', 'avalanches', 'conditions', 'conditions_levels',
    'hut_comment', 'participants', 'route_description', 'timing', 'weather'
]


class OutingLocale(_OutingLocaleMixin, DocumentLocale):
    """
    """
    __tablename__ = 'outings_locales'

    id = Column(
                Integer,
                ForeignKey(schema + '.documents_locales.id'), primary_key=True)

    def to_archive(self):
        locale = ArchiveOutingLocale()
        super(OutingLocale, self)._to_archive(locale)
        copy_attributes(self, locale, attributes_locales)

        return locale

    def update(self, other):
        super(OutingLocale, self).update(other)
        copy_attributes(other, self, attributes_locales)


class ArchiveOutingLocale(_OutingLocaleMixin, ArchiveDocumentLocale):
    """
    """
    __tablename__ = 'outings_locales_archives'

    id = Column(
        Integer,
        ForeignKey(schema + '.documents_locales_archives.id'),
        primary_key=True)

    __table_args__ = Base.__table_args__


schema_outing_locale = SQLAlchemySchemaNode(
    OutingLocale,
    # whitelisted attributes
    includes=schema_locale_attributes + attributes_locales,
    overrides={
        'version': {
            'missing': None
        }
    })

schema_outing = SQLAlchemySchemaNode(
    Outing,
    # whitelisted attributes
    includes=schema_attributes + attributes,
    overrides={
        'document_id': {
            'missing': None
        },
        'version': {
            'missing': None
        },
        'locales': {
            'children': [schema_outing_locale]
        },
        'activities': {
            'validator': colander.Length(min=1)
        },
        'geometry': get_geometry_schema_overrides(
            ['LINESTRING', 'MULTILINESTRING'])
    })

schema_create_outing = get_create_schema(schema_outing)
schema_update_outing = get_update_schema(schema_outing)
schema_association_outing = restrict_schema(schema_outing, [
    'locales.title', 'activities', 'date_start', 'date_end'
])


# ===================================================================
# Pydantic schemas (generated from the SQLAlchemy model)
# ===================================================================
from c2corg_api.models.pydantic import (  # noqa: E402, F811
    schema_from_sa_model,
    get_update_schema as pydantic_update_schema,
    get_create_schema as pydantic_create_schema,
    DocumentGeometrySchema,
    AssociationsSchema,
    LangType,
    _DuplicateLocalesMixin,
)
from typing import List, Optional  # noqa: E402

# -- outing locale schema ----------------------------------------------------

_OutingLocaleBase = schema_from_sa_model(
    OutingLocale,
    name='_OutingLocaleBase',
    includes=schema_locale_attributes + attributes_locales,
    overrides={
        'version': {'default': None},
        'lang': {'type': LangType},
    },
)


class OutingLocaleSchema(_OutingLocaleBase):
    """Locale for outing create/update requests."""
    model_config = {"extra": "ignore"}


# -- outing document schema --------------------------------------------------

_outing_schema_attrs = [
    a for a in schema_attributes + attributes
    if a not in ('locales', 'geometry')
]

_OutingDocBase = schema_from_sa_model(
    Outing,
    name='_OutingDocBase',
    includes=_outing_schema_attrs,
    overrides={
        'document_id': {'default': None},
        'version': {'default': None},
        # Accept any string for activities; downstream validators
        # (validate_document_for_type) check valid values, matching
        # the old colander behaviour.
        'activities': {'type': List[str]},
    },
)


class OutingDocumentSchema(
    _DuplicateLocalesMixin, _OutingDocBase,
):
    """Full outing document for create/update requests."""
    locales: Optional[List[OutingLocaleSchema]] = None
    geometry: Optional[DocumentGeometrySchema] = None
    associations: Optional[AssociationsSchema] = None
    model_config = {"extra": "ignore"}


CreateOutingSchema = pydantic_create_schema(
    OutingDocumentSchema,
    name='CreateOutingSchema',
)

UpdateOutingSchema = pydantic_update_schema(
    OutingDocumentSchema,
    name='UpdateOutingSchema',
)
