import datetime
from typing import Optional

from sqlalchemy import Boolean, Date, ForeignKey, Integer, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from c2corg_api.models import Base, enums, schema
from c2corg_api.models.common import document_types
from c2corg_api.models.common.fields_xreport import fields_xreport
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
from c2corg_api.models.utils import copy_attributes

XREPORT_TYPE = document_types.XREPORT_TYPE


class _XreportMixin:
    # Altitude
    elevation: Mapped[Optional[int]] = mapped_column(SmallInteger)

    # date des observations
    date: Mapped[Optional[datetime.date]] = mapped_column(Date)

    # Type d'évènement
    event_type: Mapped[Optional[str]] = mapped_column(enums.event_type)

    event_activity: Mapped[str] = mapped_column(enums.event_activity, nullable=False)

    # Nombre de participants
    nb_participants: Mapped[Optional[int]] = mapped_column(SmallInteger)

    # Nombre de personnes touchées
    nb_impacted: Mapped[Optional[int]] = mapped_column(SmallInteger)

    # Intervention des secour
    rescue: Mapped[Optional[bool]] = mapped_column(Boolean)

    avalanche_level: Mapped[Optional[str]] = mapped_column(enums.avalanche_level)

    avalanche_slope: Mapped[Optional[str]] = mapped_column(enums.avalanche_slope)

    # Proceed. of output and event-déroulement de la sortie et de l'évènement
    severity: Mapped[Optional[str]] = mapped_column(enums.severity)

    # PROFILE

    # Involvement in the accident-Implication dans l'accident
    author_status: Mapped[Optional[str]] = mapped_column(enums.author_status)

    # Frequency practical activity-Fréquence de pratique de l'activité
    activity_rate: Mapped[Optional[str]] = mapped_column(enums.activity_rate)

    age: Mapped[Optional[int]] = mapped_column(SmallInteger)

    gender: Mapped[Optional[str]] = mapped_column(enums.gender)

    # Blessures antérieures
    previous_injuries: Mapped[Optional[str]] = mapped_column(enums.previous_injuries)

    autonomy: Mapped[Optional[str]] = mapped_column(enums.autonomy)

    supervision: Mapped[Optional[str]] = mapped_column(enums.supervision)

    qualification: Mapped[Optional[str]] = mapped_column(enums.qualification)

    disable_comments: Mapped[Optional[bool]] = mapped_column(Boolean)

    anonymous: Mapped[Optional[bool]] = mapped_column(Boolean)


attributes = [
    'elevation',
    'date',
    'event_type',
    'event_activity',
    'nb_participants',
    'nb_impacted',
    'rescue',
    'avalanche_level',
    'avalanche_slope',
    'severity',
    'author_status',
    'activity_rate',
    'age',
    'gender',
    'previous_injuries',
    'autonomy',
    'supervision',
    'qualification',
    'disable_comments',
    'anonymous',
]

attributes_without_personal = [
    'elevation',
    'date',
    'event_type',
    'event_activity',
    'nb_participants',
    'nb_impacted',
    'rescue',
    'avalanche_level',
    'avalanche_slope',
    'severity',
    'disable_comments',
    'anonymous',
]


class Xreport(_XreportMixin, Document):
    """ """

    __tablename__ = 'xreports'

    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(schema + '.documents.document_id'), primary_key=True
    )

    __mapper_args__ = {
        'polymorphic_identity': XREPORT_TYPE,
        'inherit_condition': Document.document_id == document_id,
    }

    def to_archive(self):
        xreport = ArchiveXreport()
        super(Xreport, self)._to_archive(xreport)
        copy_attributes(self, xreport, attributes)
        return xreport

    def update(self, other):
        super(Xreport, self).update(other)
        copy_attributes(other, self, attributes)


class ArchiveXreport(_XreportMixin, ArchiveDocument):
    """ """

    __tablename__ = 'xreports_archives'

    id: Mapped[int] = mapped_column(
        Integer, ForeignKey(schema + '.documents_archives.id'), primary_key=True
    )

    __mapper_args__ = {
        'polymorphic_identity': XREPORT_TYPE,
        'inherit_condition': ArchiveDocument.id == id,
    }

    __table_args__ = Base.__table_args__


class _XreportLocaleMixin:
    # Event location-Lieu de l'évènement
    place: Mapped[Optional[str]] = mapped_column(String)

    # Study route-Etude de l'itinéraire
    route_study: Mapped[Optional[str]] = mapped_column(String)

    # Study conditions-Etude des conditions
    conditions: Mapped[Optional[str]] = mapped_column(String)

    # Physical preparation and training in relation to the objective
    # Préparation physique et entraînement par rapport à l'objectif
    training: Mapped[Optional[str]] = mapped_column(String)

    # Motivations
    motivations: Mapped[Optional[str]] = mapped_column(String)

    # Group dynamic-Dynamique de groupe
    group_management: Mapped[Optional[str]] = mapped_column(String)

    # Attentiveness and (revaluation risk)
    # Niveau d'attention et (ré)évaluation des risques
    risk: Mapped[Optional[str]] = mapped_column(String)

    # Management of time-Gestion du temps
    time_management: Mapped[Optional[str]] = mapped_column(String)

    # Safety measures and technical implementations
    # Mesures et techniques de sécurité mises en oeuvres
    safety: Mapped[Optional[str]] = mapped_column(String)

    # Elements that have mitigated the impact
    # Eléments qui ont atténué les conséquences
    reduce_impact: Mapped[Optional[str]] = mapped_column(String)
    increase_impact: Mapped[Optional[str]] = mapped_column(String)

    # Its practical consequences
    # Conséquences sur ses pratiques
    modifications: Mapped[Optional[str]] = mapped_column(String)

    # Physical consequences and other comments
    # Conséquences physiques et autres commentaires
    other_comments: Mapped[Optional[str]] = mapped_column(String)


attributes_locales = [
    'place',
    'route_study',
    'conditions',
    'training',
    'motivations',
    'group_management',
    'risk',
    'time_management',
    'safety',
    'reduce_impact',
    'increase_impact',
    'modifications',
    'other_comments',
]


class XreportLocale(_XreportLocaleMixin, DocumentLocale):
    """ """

    __tablename__ = 'xreports_locales'

    id: Mapped[int] = mapped_column(
        Integer, ForeignKey(schema + '.documents_locales.id'), primary_key=True
    )

    __mapper_args__ = {
        'polymorphic_identity': XREPORT_TYPE,
        'inherit_condition': DocumentLocale.id == id,
    }

    def to_archive(self):
        locale = ArchiveXreportLocale()
        super(XreportLocale, self)._to_archive(locale)
        copy_attributes(self, locale, attributes_locales)

        return locale

    def update(self, other):
        super(XreportLocale, self).update(other)
        copy_attributes(other, self, attributes_locales)


class ArchiveXreportLocale(_XreportLocaleMixin, ArchiveDocumentLocale):
    """ """

    __tablename__ = 'xreports_locales_archives'

    id: Mapped[int] = mapped_column(
        Integer, ForeignKey(schema + '.documents_locales_archives.id'), primary_key=True
    )

    __mapper_args__ = {
        'polymorphic_identity': XREPORT_TYPE,
        'inherit_condition': ArchiveDocumentLocale.id == id,
    }

    __table_args__ = Base.__table_args__


_xreport_locale_fields = schema_locale_attributes + attributes_locales

schema_xreport = build_field_spec(
    Xreport,
    includes=schema_attributes + attributes,
    locale_fields=_xreport_locale_fields,
    geometry_fields=geometry_attributes,
)

# schema that hides personal information of a xreport
schema_xreport_without_personal = build_field_spec(
    Xreport,
    includes=schema_attributes + attributes_without_personal,
    locale_fields=_xreport_locale_fields,
    geometry_fields=geometry_attributes,
)

schema_listing_xreport = schema_xreport.restrict(fields_xreport.get('listing'))
