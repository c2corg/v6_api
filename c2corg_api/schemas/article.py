"""Schemas of the articles."""

from c2corg_api.models.article import Article
from c2corg_api.models.common import attributes as a
from c2corg_api.models.common.attributes import article_types
from c2corg_api.models.common.fields_article import fields_article
from c2corg_api.schemas.base import ModelSchema, create_schema, update_schema
from c2corg_api.schemas.document import (
    AssociationsSchema,
    DocumentSchema,
    document_children,
)
from c2corg_api.schemas.types import OneOf, Seq


class ArticleSchema(DocumentSchema):
    # no geometry: articles are not on the map
    categories: Seq(OneOf(a.article_categories)) = None
    activities: Seq(OneOf(a.activities)) = None
    article_type: OneOf(article_types) = None


ArticleCreateSchema = create_schema(ArticleSchema, AssociationsSchema)
ArticleUpdateSchema = update_schema(ArticleCreateSchema)

article_schema = ModelSchema(Article, ArticleSchema, document_children())
article_listing_schema = article_schema.restrict(fields_article.get('listing'))
