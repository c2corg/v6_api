"""Schemas of the incident and accident reports (xreports)."""

from c2corg_api.models.common import attributes as a
from c2corg_api.models.common.fields_xreport import fields_xreport
from c2corg_api.models.xreport import Xreport, XreportLocale
from c2corg_api.schemas.base import ModelSchema, create_schema, update_schema
from c2corg_api.schemas.document import (
    AssociationsSchema,
    DocumentSchema,
    LocaleSchema,
    document_children,
    geometry_schema,
)
from c2corg_api.schemas.types import Bool, Date, Int, Map, OneOf, Seq, Str

XreportGeometrySchema = geometry_schema(['POINT'])


class XreportLocaleSchema(LocaleSchema):
    place: Str() = None
    route_study: Str() = None
    conditions: Str() = None
    training: Str() = None
    motivations: Str() = None
    group_management: Str() = None
    risk: Str() = None
    time_management: Str() = None
    safety: Str() = None
    reduce_impact: Str() = None
    increase_impact: Str() = None
    modifications: Str() = None
    other_comments: Str() = None


class XreportSchema(DocumentSchema):
    locales: Seq(XreportLocaleSchema) = []
    geometry: Map(XreportGeometrySchema) = None
    elevation: Int = None
    date: Date = None
    event_type: OneOf(a.event_types) = None
    event_activity: OneOf(a.event_activities)
    nb_participants: Int = None
    nb_impacted: Int = None
    rescue: Bool = None
    avalanche_level: OneOf(a.avalanche_levels) = None
    avalanche_slope: OneOf(a.avalanche_slopes) = None
    severity: OneOf(a.severities) = None
    # personal information, only shown to the author and moderators
    author_status: OneOf(a.author_statuses) = None
    activity_rate: OneOf(a.activity_rates) = None
    age: Int = None
    gender: OneOf(a.genders) = None
    previous_injuries: OneOf(a.previous_injuries) = None
    autonomy: OneOf(a.autonomies) = None
    supervision: OneOf(a.supervision) = None
    qualification: OneOf(a.qualification) = None
    disable_comments: Bool = None
    anonymous: Bool = None


PERSONAL_FIELDS = [
    'author_status',
    'activity_rate',
    'age',
    'gender',
    'previous_injuries',
    'autonomy',
    'supervision',
    'qualification',
]

XreportCreateSchema = create_schema(XreportSchema, AssociationsSchema)
XreportUpdateSchema = update_schema(XreportCreateSchema)

xreport_schema = ModelSchema(
    Xreport,
    XreportSchema,
    document_children(
        locale_schema=XreportLocaleSchema,
        locale_model=XreportLocale,
        geometry=XreportGeometrySchema,
    ),
)
xreport_without_personal_schema = xreport_schema.only(
    [name for name in xreport_schema.fields if name not in PERSONAL_FIELDS]
)
xreport_listing_schema = xreport_schema.restrict(fields_xreport.get('listing'))
