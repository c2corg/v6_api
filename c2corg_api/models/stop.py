from c2corg_api.models.schema_utils import restrict_schema, \
    get_update_schema, get_create_schema
from sqlalchemy import ( Column, Integer, String, ForeignKey)

from colanderalchemy import SQLAlchemySchemaNode

from c2corg_api.models import schema, Base
from c2corg_api.models.utils import copy_attributes
from c2corg_api.models.common import document_types
from c2corg_api.models.document import ( Document, schema_attributes, get_geometry_schema_overrides)

STOP_TYPE = document_types.STOP_TYPE


class _StopMixin(object):
    navitia_id = Column(String, nullable=False)
    stop_name = Column(String, nullable=False)
    line = Column(String, nullable=False)
    operator = Column(String, nullable=False)


attributes = ['navitia_id','stop_name', 'line', 'operator']


class Stop(_StopMixin, Document):
    """
    """
    __tablename__ = 'stops'
    __table_args__ = {
        'schema': schema,
        'extend_existing': True
    }

    document_id = Column(
        Integer,
        ForeignKey(schema + '.documents.document_id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': STOP_TYPE,
        'inherit_condition': Document.document_id == document_id
    }

    def update(self, other):
        super(Stop, self).update(other)
        copy_attributes(other, self, attributes)

    def to_dict(self):
        return {
            "id": self.document_id,
            "navitia_id":self.navitia_id,
            "stop_name": self.stop_name,
            "line": self.line,
            "operator": self.operator,
        }


schema_stop = SQLAlchemySchemaNode(
    Stop,
    includes=schema_attributes + attributes,
    overrides={
        'document_id': {'missing': None},
        'version': {'missing': None},
        'geometry': get_geometry_schema_overrides(['POINT'])
    }
)

schema_create_stop = get_create_schema(schema_stop)
schema_update_stop = get_update_schema(schema_stop)
