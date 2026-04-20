from datetime import date
from typing import List, Optional

from sqlalchemy import Boolean, Date, ForeignKey, Integer, SmallInteger, String
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

OUTING_TYPE = document_types.OUTING_TYPE


class _OutingMixin:
    activities: Mapped[List[str]] = mapped_column(
        ArrayOfEnum(enums.activity_type), nullable=False
    )

    date_start: Mapped[date] = mapped_column(Date, nullable=False)

    date_end: Mapped[date] = mapped_column(Date, nullable=False)

    frequentation: Mapped[Optional[str]] = mapped_column(enums.frequentation_type)

    participant_count: Mapped[Optional[int]] = mapped_column(SmallInteger)

    elevation_min: Mapped[Optional[int]] = mapped_column(SmallInteger)

    elevation_max: Mapped[Optional[int]] = mapped_column(SmallInteger)

    elevation_access: Mapped[Optional[int]] = mapped_column(SmallInteger)

    # altitude de chaussage
    elevation_up_snow: Mapped[Optional[int]] = mapped_column(SmallInteger)

    # altitude de dechaussage
    elevation_down_snow: Mapped[Optional[int]] = mapped_column(SmallInteger)

    height_diff_up: Mapped[Optional[int]] = mapped_column(SmallInteger)

    height_diff_down: Mapped[Optional[int]] = mapped_column(SmallInteger)

    length_total: Mapped[Optional[int]] = mapped_column(Integer)

    partial_trip: Mapped[Optional[bool]] = mapped_column(Boolean)

    public_transport: Mapped[Optional[bool]] = mapped_column(Boolean)

    access_condition: Mapped[Optional[str]] = mapped_column(enums.access_condition)

    lift_status: Mapped[Optional[str]] = mapped_column(enums.lift_status)

    condition_rating: Mapped[Optional[str]] = mapped_column(enums.condition_rating)

    snow_quantity: Mapped[Optional[str]] = mapped_column(enums.snow_quantity_ratings)

    snow_quality: Mapped[Optional[str]] = mapped_column(enums.snow_quality_ratings)

    glacier_rating: Mapped[Optional[str]] = mapped_column(enums.glacier_rating)

    avalanche_signs: Mapped[Optional[List[str]]] = mapped_column(
        ArrayOfEnum(enums.avalanche_signs)
    )

    hut_status: Mapped[Optional[str]] = mapped_column(enums.hut_status)

    disable_comments: Mapped[Optional[bool]] = mapped_column(Boolean)

    hiking_rating: Mapped[Optional[str]] = mapped_column(enums.hiking_rating)

    ski_rating: Mapped[Optional[str]] = mapped_column(enums.ski_rating)

    labande_global_rating: Mapped[Optional[str]] = mapped_column(enums.global_rating)

    snowshoe_rating: Mapped[Optional[str]] = mapped_column(enums.snowshoe_rating)

    global_rating: Mapped[Optional[str]] = mapped_column(enums.global_rating)

    height_diff_difficulties: Mapped[Optional[int]] = mapped_column(SmallInteger)

    engagement_rating: Mapped[Optional[str]] = mapped_column(enums.engagement_rating)

    equipment_rating: Mapped[Optional[str]] = mapped_column(enums.equipment_rating)

    rock_free_rating: Mapped[Optional[str]] = mapped_column(enums.climbing_rating)

    ice_rating: Mapped[Optional[str]] = mapped_column(enums.ice_rating)

    via_ferrata_rating: Mapped[Optional[str]] = mapped_column(enums.via_ferrata_rating)

    mtb_up_rating: Mapped[Optional[str]] = mapped_column(enums.mtb_up_rating)

    mtb_down_rating: Mapped[Optional[str]] = mapped_column(enums.mtb_down_rating)


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
    """ """

    __tablename__ = 'outings'

    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(schema + '.documents.document_id'), primary_key=True
    )

    __mapper_args__ = {
        'polymorphic_identity': OUTING_TYPE,
        'inherit_condition': Document.document_id == document_id,
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
    """ """

    __tablename__ = 'outings_archives'

    id: Mapped[int] = mapped_column(
        Integer, ForeignKey(schema + '.documents_archives.id'), primary_key=True
    )

    __mapper_args__ = {
        'polymorphic_identity': OUTING_TYPE,
        'inherit_condition': ArchiveDocument.id == id,
    }

    __table_args__ = Base.__table_args__


class _OutingLocaleMixin:
    __mapper_args__ = {'polymorphic_identity': OUTING_TYPE}

    participants: Mapped[Optional[str]] = mapped_column(String)

    access_comment: Mapped[Optional[str]] = mapped_column(String)

    weather: Mapped[Optional[str]] = mapped_column(String)

    timing: Mapped[Optional[str]] = mapped_column(String)

    conditions_levels: Mapped[Optional[str]] = mapped_column(String)

    conditions: Mapped[Optional[str]] = mapped_column(String)

    avalanches: Mapped[Optional[str]] = mapped_column(String)

    hut_comment: Mapped[Optional[str]] = mapped_column(String)

    route_description: Mapped[Optional[str]] = mapped_column(String)


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
    """ """

    __tablename__ = 'outings_locales'

    id: Mapped[int] = mapped_column(
        Integer, ForeignKey(schema + '.documents_locales.id'), primary_key=True
    )

    def to_archive(self):
        locale = ArchiveOutingLocale()
        super(OutingLocale, self)._to_archive(locale)
        copy_attributes(self, locale, attributes_locales)

        return locale

    def update(self, other):
        super(OutingLocale, self).update(other)
        copy_attributes(other, self, attributes_locales)


class ArchiveOutingLocale(_OutingLocaleMixin, ArchiveDocumentLocale):
    """ """

    __tablename__ = 'outings_locales_archives'

    id: Mapped[int] = mapped_column(
        Integer, ForeignKey(schema + '.documents_locales_archives.id'), primary_key=True
    )

    __table_args__ = Base.__table_args__


schema_outing = build_field_spec(
    Outing,
    includes=schema_attributes + attributes,
    locale_fields=schema_locale_attributes + attributes_locales,
    geometry_fields=geometry_attributes,
)
