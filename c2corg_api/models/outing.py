import colander
from c2corg_api.models.schema_utils import restrict_schema
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
from colander import MappingSchema, SchemaNode, Integer as ColanderInteger, \
    Sequence

from c2corg_api.models import schema
from c2corg_api.models.utils import ArrayOfEnum
from c2corg_api.models.utils import copy_attributes
from c2corg_api.models.document import (
    ArchiveDocument, Document, DocumentLocale, ArchiveDocumentLocale,
    get_update_schema, geometry_schema_overrides, schema_locale_attributes,
    schema_attributes)
from c2corg_api.models import enums

OUTING_TYPE = 'o'


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

    awesomeness = Column(enums.awesomeness)

    duration = Column(SmallInteger)

    duration_difficulties = Column(SmallInteger)

    condition_rating = Column(enums.condition_rating)

    snow_quantity = Column(enums.condition_rating)

    snow_quality = Column(enums.condition_rating)

    glacier_rating = Column(enums.glacier_rating)

    avalanche_signs = Column(ArrayOfEnum(enums.avalanche_signs))

    hut_status = Column(enums.hut_status)

attributes = [
    'access_condition', 'activities', 'avalanche_signs', 'awesomeness',
    'condition_rating', 'date_end', 'date_start', 'duration',
    'duration_difficulties', 'elevation_access', 'elevation_down_snow',
    'elevation_max', 'elevation_min', 'elevation_up_snow', 'frequentation',
    'glacier_rating', 'height_diff_down', 'height_diff_up', 'hut_status',
    'length_total', 'lift_status', 'partial_trip', 'participant_count',
    'public_transport', 'snow_quality', 'snow_quantity']


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
        'geometry': geometry_schema_overrides
    })


class CreateOutingSchema(MappingSchema):
    """The schema used for the web-service to create a new outing.
    """
    route_id = SchemaNode(ColanderInteger())
    user_ids = SchemaNode(Sequence(),
                          SchemaNode(ColanderInteger()),
                          validator=colander.Length(min=1))
    outing = schema_outing.clone()

schema_create_outing = CreateOutingSchema()
schema_update_outing = get_update_schema(schema_outing)
schema_association_outing = restrict_schema(schema_outing, [
    'locales.title', 'activities'
])
