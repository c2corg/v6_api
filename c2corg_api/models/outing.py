from sqlalchemy import Boolean, Column, Date, ForeignKey, Integer, SmallInteger, String

from c2corg_api.models import Base, enums, schema
from c2corg_api.models.common import document_types
from c2corg_api.models.document import (
    ArchiveDocument,
    ArchiveDocumentLocale,
    Document,
    DocumentLocale,
)
from c2corg_api.models.utils import ArrayOfEnum, copy_attributes

OUTING_TYPE = document_types.OUTING_TYPE


class _OutingMixin:
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
    'access_condition',
    'activities',
    'avalanche_signs',
    'condition_rating',
    'date_end',
    'date_start',
    'elevation_access',
    'elevation_down_snow',
    'elevation_max',
    'elevation_min',
    'elevation_up_snow',
    'frequentation',
    'glacier_rating',
    'height_diff_down',
    'height_diff_up',
    'hut_status',
    'length_total',
    'lift_status',
    'partial_trip',
    'participant_count',
    'public_transport',
    'snow_quality',
    'snow_quantity',
    'disable_comments',
    'hiking_rating',
    'ski_rating',
    'labande_global_rating',
    'ice_rating',
    'snowshoe_rating',
    'global_rating',
    'height_diff_difficulties',
    'engagement_rating',
    'equipment_rating',
    'rock_free_rating',
    'via_ferrata_rating',
    'mtb_up_rating',
    'mtb_down_rating',
]


class Outing(_OutingMixin, Document):
    """Current version of an outing."""

    __tablename__ = 'outings'

    document_id = Column(
        Integer, ForeignKey(schema + '.documents.document_id'), primary_key=True
    )

    __mapper_args__ = {
        'polymorphic_identity': OUTING_TYPE,
        'inherit_condition': Document.document_id == document_id,
    }

    def to_archive(self):
        outing = ArchiveOuting()
        super()._to_archive(outing)
        copy_attributes(self, outing, attributes)

        return outing

    def update(self, other):
        super().update(other)
        copy_attributes(other, self, attributes)


class ArchiveOuting(_OutingMixin, ArchiveDocument):
    """Archived version of an outing."""

    __tablename__ = 'outings_archives'

    id = Column(
        Integer, ForeignKey(schema + '.documents_archives.id'), primary_key=True
    )

    __mapper_args__ = {
        'polymorphic_identity': OUTING_TYPE,
        'inherit_condition': ArchiveDocument.id == id,
    }

    __table_args__ = Base.__table_args__


class _OutingLocaleMixin:
    __mapper_args__ = {'polymorphic_identity': OUTING_TYPE}

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
    'access_comment',
    'avalanches',
    'conditions',
    'conditions_levels',
    'hut_comment',
    'participants',
    'route_description',
    'timing',
    'weather',
]


class OutingLocale(_OutingLocaleMixin, DocumentLocale):
    """Current version of an outing locale."""

    __tablename__ = 'outings_locales'

    id = Column(Integer, ForeignKey(schema + '.documents_locales.id'), primary_key=True)

    def to_archive(self):
        locale = ArchiveOutingLocale()
        super()._to_archive(locale)
        copy_attributes(self, locale, attributes_locales)

        return locale

    def update(self, other):
        super().update(other)
        copy_attributes(other, self, attributes_locales)


class ArchiveOutingLocale(_OutingLocaleMixin, ArchiveDocumentLocale):
    """Archived version of an outing locale."""

    __tablename__ = 'outings_locales_archives'

    id = Column(
        Integer, ForeignKey(schema + '.documents_locales_archives.id'), primary_key=True
    )

    __table_args__ = Base.__table_args__
