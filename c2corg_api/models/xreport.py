from c2corg_api.models.field_spec import build_field_spec
from c2corg_api.models.common.fields_xreport import fields_xreport
from sqlalchemy import (
    Column,
    Integer,
    Boolean,
    SmallInteger,
    ForeignKey,
    String,
    Date
    )

from c2corg_api.models import schema, Base
from c2corg_api.models.utils import copy_attributes
from c2corg_api.models.document import (
    ArchiveDocument,
    Document,
    schema_attributes, DocumentLocale, ArchiveDocumentLocale,
    schema_locale_attributes, geometry_attributes)
from c2corg_api.models.common import document_types
from c2corg_api.models import enums

XREPORT_TYPE = document_types.XREPORT_TYPE


class _XreportMixin(object):

    # Altitude
    elevation = Column(SmallInteger)

    # date des observations
    date = Column(Date)

    # Type d'évènement
    event_type = Column(enums.event_type)

    event_activity = Column(enums.event_activity, nullable=False)

    # Nombre de participants
    nb_participants = Column(SmallInteger)

    # Nombre de personnes touchées
    nb_impacted = Column(SmallInteger)

    # Intervention des secour
    rescue = Column(Boolean)

    avalanche_level = Column(enums.avalanche_level)

    avalanche_slope = Column(enums.avalanche_slope)

    # Proceed. of output and event-déroulement de la sortie et de l'évènement
    severity = Column(enums.severity)

    # PROFILE

    # Involvement in the accident-Implication dans l'accident
    author_status = Column(enums.author_status)

    # Frequency practical activity-Fréquence de pratique de l'activité
    activity_rate = Column(enums.activity_rate)

    age = Column(SmallInteger)

    gender = Column(enums.gender)

    # Blessures antérieures
    previous_injuries = Column(enums.previous_injuries)

    autonomy = Column(enums.autonomy)

    supervision = Column(enums.supervision)

    qualification = Column(enums.qualification)

    disable_comments = Column(Boolean)

    anonymous = Column(Boolean)


attributes = [
    'elevation', 'date', 'event_type', 'event_activity',
    'nb_participants', 'nb_impacted', 'rescue',
    'avalanche_level', 'avalanche_slope', 'severity',
    'author_status', 'activity_rate', 'age', 'gender',
    'previous_injuries', 'autonomy', 'supervision', 'qualification',
    'disable_comments', 'anonymous'
]

attributes_without_personal = [
    'elevation', 'date', 'event_type', 'event_activity',
    'nb_participants', 'nb_impacted', 'rescue',
    'avalanche_level', 'avalanche_slope', 'severity',
    'disable_comments', 'anonymous'
]


class Xreport(_XreportMixin, Document):
    """
    """
    __tablename__ = 'xreports'

    document_id = Column(
        Integer,
        ForeignKey(schema + '.documents.document_id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': XREPORT_TYPE,
        'inherit_condition': Document.document_id == document_id
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
    """
    """
    __tablename__ = 'xreports_archives'

    id = Column(
        Integer,
        ForeignKey(schema + '.documents_archives.id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': XREPORT_TYPE,
        'inherit_condition': ArchiveDocument.id == id
    }

    __table_args__ = Base.__table_args__


class _XreportLocaleMixin(object):
    # Event location-Lieu de l'évènement
    place = Column(String)

    # Study route-Etude de l'itinéraire
    route_study = Column(String)

    # Study conditions-Etude des conditions
    conditions = Column(String)

    # Physical preparation and training in relation to the objective
    # Préparation physique et entraînement par rapport à l'objectif
    training = Column(String)

    # Motivations
    motivations = Column(String)

    # Group dynamic-Dynamique de groupe
    group_management = Column(String)

    # Attentiveness and (revaluation risk)
    # Niveau d'attention et (ré)évaluation des risques
    risk = Column(String)

    # Management of time-Gestion du temps
    time_management = Column(String)

    # Safety measures and technical implementations
    # Mesures et techniques de sécurité mises en oeuvres
    safety = Column(String)

    # Elements that have mitigated the impact
    # Eléments qui ont atténué les conséquences
    reduce_impact = Column(String)
    increase_impact = Column(String)

    # Its practical consequences
    # Conséquences sur ses pratiques
    modifications = Column(String)

    # Physical consequences and other comments
    # Conséquences physiques et autres commentaires
    other_comments = Column(String)


attributes_locales = [
    'place', 'route_study', 'conditions', 'training', 'motivations',
    'group_management', 'risk', 'time_management', 'safety',
    'reduce_impact', 'increase_impact',
    'modifications', 'other_comments'
]


class XreportLocale(_XreportLocaleMixin, DocumentLocale):
    """
    """
    __tablename__ = 'xreports_locales'

    id = Column(
        Integer,
        ForeignKey(schema + '.documents_locales.id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': XREPORT_TYPE,
        'inherit_condition': DocumentLocale.id == id
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
    """
    """
    __tablename__ = 'xreports_locales_archives'

    id = Column(
        Integer,
        ForeignKey(schema + '.documents_locales_archives.id'),
        primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': XREPORT_TYPE,
        'inherit_condition': ArchiveDocumentLocale.id == id
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

schema_listing_xreport = schema_xreport.restrict(
    fields_xreport.get('listing')
)


# ===================================================================
# Pydantic schemas (generated from the SQLAlchemy model)
# ===================================================================
from c2corg_api.models.pydantic import (  # noqa: E402
    schema_from_sa_model,
    get_update_schema as pydantic_update_schema,
    get_create_schema as pydantic_create_schema,
    DocumentLocaleSchema,
    DocumentGeometrySchema,
    AssociationsSchema,
    _DuplicateLocalesMixin,
)
from typing import List, Optional  # noqa: E402

_xreport_locale_attrs = [
    a for a in schema_locale_attributes + attributes_locales
]

_XreportLocaleBase = schema_from_sa_model(
    XreportLocale,
    name='_XreportLocaleBase',
    includes=_xreport_locale_attrs,
    overrides={
        'version': {'default': None},
    },
)


class XreportLocaleSchema(DocumentLocaleSchema, _XreportLocaleBase):
    """Xreport locale with extra fields (place, conditions, etc.)."""
    pass


_xreport_schema_attrs = [
    a for a in schema_attributes + attributes
    if a not in ('locales', 'geometry')
]

_XreportDocBase = schema_from_sa_model(
    Xreport,
    name='_XreportDocBase',
    includes=_xreport_schema_attrs,
    overrides={
        'document_id': {'default': None},
        'version': {'default': None},
        'event_activity': {'default': ...},
    },
)


class XreportDocumentSchema(
    _DuplicateLocalesMixin, _XreportDocBase,
):
    """Full xreport document for create/update requests."""
    locales: Optional[List[XreportLocaleSchema]] = None
    geometry: Optional[DocumentGeometrySchema] = None
    associations: Optional[AssociationsSchema] = None
    model_config = {"extra": "ignore"}


CreateXreportSchema = pydantic_create_schema(
    XreportDocumentSchema,
    name='CreateXreportSchema',
)

UpdateXreportSchema = pydantic_update_schema(
    XreportDocumentSchema,
    name='UpdateXreportSchema',
)
