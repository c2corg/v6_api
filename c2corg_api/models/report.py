import colander
from c2corg_api.models.schema_utils import restrict_schema,\
    get_update_schema, get_create_schema
from c2corg_common.fields_report import fields_report
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
    geometry_schema_overrides,
    schema_attributes, DocumentLocale, ArchiveDocumentLocale,
    schema_locale_attributes)
from c2corg_common import document_types
from c2corg_api.models import enums

REPORT_TYPE = document_types.REPORT_TYPE


class _ReportMixin(object):
    # Event characterization-Caractérisation de l'évènement

    # Altitude
    elevation = Column(SmallInteger)

    # date des observations
    date = Column(Date)  # , nullable=False

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


attributes = [
    'elevation', 'date', 'event_type', 'activities',
    'nb_participants', 'nb_impacted', 'rescue',
    'avalanche_level', 'avalanche_slope', 'severity',
    'author_status', 'activity_rate', 'nb_outings', 'age', 'gender',
    'previous_injuries', 'autonomy'
]

attributes_without_personal = [
    'lon', 'lat', 'elevation', 'date', 'event_type', 'activities',
    'nb_participants', 'nb_impacted', 'rescue',
    'avalanche_level', 'avalanche_slope', 'severity'
]


class Report(_ReportMixin, Document):
    """
    """
    __tablename__ = 'reports'

    document_id = Column(
        Integer,
        ForeignKey(schema + '.documents.document_id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': REPORT_TYPE,
        'inherit_condition': Document.document_id == document_id
    }

    def to_archive(self):
        report = ArchiveReport()
        super(Report, self)._to_archive(report)
        copy_attributes(self, report, attributes)
        return report

    def update(self, other):
        super(Report, self).update(other)
        copy_attributes(other, self, attributes)


class ArchiveReport(_ReportMixin, ArchiveDocument):
    """
    """
    __tablename__ = 'reports_archives'

    id = Column(
        Integer,
        ForeignKey(schema + '.documents_archives.id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': REPORT_TYPE,
        'inherit_condition': ArchiveDocument.id == id
    }

    __table_args__ = Base.__table_args__


class _ReportLocaleMixin(object):
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


class ReportLocale(_ReportLocaleMixin, DocumentLocale):
    """
    """
    __tablename__ = 'reports_locales'

    id = Column(
        Integer,
        ForeignKey(schema + '.documents_locales.id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': REPORT_TYPE,
        'inherit_condition': DocumentLocale.id == id
    }

    def to_archive(self):
        locale = ArchiveReportLocale()
        super(ReportLocale, self)._to_archive(locale)
        copy_attributes(self, locale, attributes_locales)

        return locale

    def update(self, other):
        super(ReportLocale, self).update(other)
        copy_attributes(other, self, attributes_locales)


class ArchiveReportLocale(_ReportLocaleMixin, ArchiveDocumentLocale):
    """
    """
    __tablename__ = 'reports_locales_archives'

    id = Column(
        Integer,
        ForeignKey(schema + '.documents_locales_archives.id'),
        primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': REPORT_TYPE,
        'inherit_condition': ArchiveDocumentLocale.id == id
    }

    __table_args__ = Base.__table_args__


schema_report_locale = SQLAlchemySchemaNode(
    ReportLocale,
    # whitelisted attributes
    includes=schema_locale_attributes + attributes_locales,
    overrides={
        'version': {
            'missing': None
        }
    })

schema_report = SQLAlchemySchemaNode(
    Report,
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
            'children': [schema_report_locale],
        },
        'activities': {
            'validator': colander.Length(min=1)
        },
        'geometry': geometry_schema_overrides
    })

schema_report_without_personal = SQLAlchemySchemaNode(
    Report,
    # whitelisted attributes
    includes=schema_attributes + attributes_without_personal,
    overrides={
        'document_id': {
            'missing': None
        },
        'version': {
            'missing': None
        },
        'locales': {
            'children': [schema_report_locale],
        },
        'activities': {
            'validator': colander.Length(min=1)
        },
        'geometry': geometry_schema_overrides
    })


schema_create_report = get_create_schema(schema_report)
schema_update_report = get_update_schema(schema_report)
schema_listing_report = restrict_schema(
    schema_report,
    fields_report.get('listing')
)
