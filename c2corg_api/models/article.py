from c2corg_api.models import schema, Base, enums
from c2corg_api.models.document import (
    ArchiveDocument, Document, schema_document_locale, schema_attributes)
from c2corg_api.models.enums import article_category, activity_type
from c2corg_api.models.schema_utils import get_update_schema, \
    restrict_schema, get_create_schema
from c2corg_api.models.utils import copy_attributes, ArrayOfEnum
from c2corg_common.fields_article import fields_article
from colanderalchemy import SQLAlchemySchemaNode
from sqlalchemy import (
    Column,
    Integer,
    ForeignKey
    )
from c2corg_common import document_types

ARTICLE_TYPE = document_types.ARTICLE_TYPE


class _ArticleMixin(object):
    categories = Column(ArrayOfEnum(article_category))
    activities = Column(ArrayOfEnum(activity_type))
    article_type = Column(enums.article_type)

attributes = ['categories', 'activities', 'article_type']


class Article(_ArticleMixin, Document):
    __tablename__ = 'articles'

    document_id = Column(
        Integer,
        ForeignKey(schema + '.documents.document_id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': ARTICLE_TYPE,
        'inherit_condition': Document.document_id == document_id
    }

    def to_archive(self):
        article = ArchiveArticle()
        super(Article, self)._to_archive(article)
        copy_attributes(self, article, attributes)

        return article

    def update(self, other):
        super(Article, self).update(other)
        copy_attributes(other, self, attributes)


class ArchiveArticle(_ArticleMixin, ArchiveDocument):
    __tablename__ = 'articles_archives'

    id = Column(
        Integer,
        ForeignKey(schema + '.documents_archives.id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': ARTICLE_TYPE,
        'inherit_condition': ArchiveDocument.id == id
    }

    __table_args__ = Base.__table_args__

schema_article_locale = schema_document_locale
schema_article_attributes = list(schema_attributes)
schema_article_attributes.remove('geometry')

schema_article = SQLAlchemySchemaNode(
    Article,
    # whitelisted attributes
    includes=schema_article_attributes + attributes,
    overrides={
        'document_id': {
            'missing': None
        },
        'version': {
            'missing': None
        },
        'locales': {
            'children': [schema_article_locale]
        },
    })

schema_create_article = get_create_schema(schema_article)
schema_update_article = get_update_schema(schema_article)
schema_listing_article = restrict_schema(
    schema_article, fields_article.get('listing'))
