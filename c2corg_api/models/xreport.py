import colander
from c2corg_api.models.schema_utils import restrict_schema,\
    get_update_schema, get_create_schema
from c2corg_common.fields_xreport import fields_xreport
from sqlalchemy import (
    Column,
    Integer,
    Boolean,
    SmallInteger,
    ForeignKey,
    String,
    Date
    )

from colanderalchemy import SQLAlchemySchemaNode

from c2corg_api.models import schema, Base
from c2corg_api.models.utils import ArrayOfEnum
from c2corg_api.models.utils import copy_attributes
from c2corg_api.models.document import (
    ArchiveDocument,
    Document,
    get_geometry_schema_overrides,
    schema_attributes, DocumentLocale, ArchiveDocumentLocale,
    schema_locale_attributes)
from c2corg_common import document_types
from c2corg_api.models import enums

XREPORT_TYPE = document_types.XREPORT_TYPE


class _XreportMixin(object):

    # Altitude
    elevation = Column(SmallInteger)

    # date des observations
    date = Column(Date)

    # Type d'évènement
    event_type = Column(ArrayOfEnum(enums.event_type))

    activities = Column(ArrayOfEnum(enums.activity_type), nullable=False)

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

    # Total trips made during the year-Nombre sorties réalisées dans l'année
    nb_outings = Column(enums.nb_outings)

    age = Column(SmallInteger)

    gender = Column(enums.gender)

    # Blessures antérieures
    previous_injuries = Column(enums.previous_injuries)

    autonomy = Column(enums.autonomy)

    disable_comments = Column(Boolean)

    anonymous = Column(Boolean)


attributes = [
    'elevation', 'date', 'event_type', 'activities',
    'nb_participants', 'nb_impacted', 'rescue',
    'avalanche_level', 'avalanche_slope', 'severity',
    'author_status', 'activity_rate', 'nb_outings', 'age', 'gender',
    'previous_injuries', 'autonomy', 'disable_comments', 'anonymous'
]

attributes_without_personal = [
    'elevation', 'date', 'event_type', 'activities',
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


schema_xreport_locale = SQLAlchemySchemaNode(
    XreportLocale,
    # whitelisted attributes
    includes=schema_locale_attributes + attributes_locales,
    overrides={
        'version': {
            'missing': None
        }
    })

schema_xreport = SQLAlchemySchemaNode(
    Xreport,
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
            'children': [schema_xreport_locale],
        },
        'activities': {
            'validator': colander.Length(min=1)
        },
        'geometry': get_geometry_schema_overrides(['POINT'])
    })

# schema that hides personal information of a xreport
schema_xreport_without_personal = SQLAlchemySchemaNode(
    Xreport,
    # whitelisted attributes
    includes=schema_attributes + attributes_without_personal,
    overrides={
        'locales': {
            'children': [schema_xreport_locale],
        },
        'geometry': get_geometry_schema_overrides(['POINT'])
    })


schema_create_xreport = get_create_schema(schema_xreport)
schema_update_xreport = get_update_schema(schema_xreport)
schema_listing_xreport = restrict_schema(
    schema_xreport,
    fields_xreport.get('listing')
)
