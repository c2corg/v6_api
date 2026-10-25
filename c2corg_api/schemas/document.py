"""Schemas shared by all document types: locales, geometry, associations."""

from c2corg_api.models.common.attributes import quality_types
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.schemas.base import ModelSchema, Schema
from c2corg_api.schemas.geometry import Geometry
from c2corg_api.schemas.types import Int, OneOf, Seq, Str


class LocaleSchema(Schema):
    version: Int = None
    lang: Str(2)
    title: Str(150)
    description: Str() = None
    summary: Str() = None


class AssociatedDocument(Schema):
    document_id: Int


class AssociationsSchema(Schema):
    users: Seq(AssociatedDocument) = None
    routes: Seq(AssociatedDocument) = None
    xreports: Seq(AssociatedDocument) = None
    waypoints: Seq(AssociatedDocument) = None
    waypoint_children: Seq(AssociatedDocument) = None
    books: Seq(AssociatedDocument) = None
    images: Seq(AssociatedDocument) = None
    articles: Seq(AssociatedDocument) = None
    outings: Seq(AssociatedDocument) = None
    coverages: Seq(AssociatedDocument) = None


def geometry_schema(geometry_types):
    """Return the geometry schema of a document type."""
    # `geom` is always a point (the position on the map); `geom_detail` is one
    # of the given geometry types.

    class GeometrySchema(Schema):
        version: Int = None
        geom: Geometry(['POINT']) = None
        geom_detail: Geometry(geometry_types) = None

    return GeometrySchema


class DocumentSchema(Schema):
    """The fields of every document type."""

    document_id: Int = None
    version: Int = None
    locales: Seq(LocaleSchema) = []
    quality: OneOf(quality_types) = 'draft'


def document_children(
    locale_schema=LocaleSchema, locale_model=DocumentLocale, geometry=None
):
    """Return the ModelSchema of the relationships of a document type."""
    children = {'locales': ModelSchema(locale_model, locale_schema)}
    if geometry is not None:
        children['geometry'] = ModelSchema(DocumentGeometry, geometry)
    return children
