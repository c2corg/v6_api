from typing import List, Optional  # noqa: E402

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from c2corg_api.models import Base, DBSession, enums, schema
from c2corg_api.models.common import document_types
from c2corg_api.models.common.fields_article import fields_article
from c2corg_api.models.document import (
    ArchiveDocument,
    Document,
    schema_attributes,
    schema_locale_attributes,
)
from c2corg_api.models.enums import activity_type, article_category
from c2corg_api.models.field_spec import build_field_spec
from c2corg_api.models.utils import ArrayOfEnum, copy_attributes

ARTICLE_TYPE = document_types.ARTICLE_TYPE


class _ArticleMixin:
    categories: Mapped[Optional[List[str]]] = mapped_column(
        ArrayOfEnum(article_category)
    )
    activities: Mapped[Optional[List[str]]] = mapped_column(ArrayOfEnum(activity_type))
    article_type: Mapped[Optional[str]] = mapped_column(enums.article_type)


attributes = ['categories', 'activities', 'article_type']


class Article(_ArticleMixin, Document):
    __tablename__ = 'articles'

    document_id: Mapped[int] = mapped_column(
        Integer, ForeignKey(schema + '.documents.document_id'), primary_key=True
    )

    __mapper_args__ = {
        'polymorphic_identity': ARTICLE_TYPE,
        'inherit_condition': Document.document_id == document_id,
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

    id: Mapped[int] = mapped_column(
        Integer, ForeignKey(schema + '.documents_archives.id'), primary_key=True
    )

    __mapper_args__ = {
        'polymorphic_identity': ARTICLE_TYPE,
        'inherit_condition': ArchiveDocument.id == id,
    }

    __table_args__ = Base.__table_args__


schema_article_attributes = list(schema_attributes)
schema_article_attributes.remove('geometry')

schema_article = build_field_spec(
    Article,
    includes=schema_article_attributes + attributes,
    locale_fields=schema_locale_attributes,
)

schema_listing_article = schema_article.restrict(fields_article.get('listing'))


def is_personal(article_id):
    article_type = (
        DBSession.query(Article.article_type)
        .select_from(Article.__table__)
        .filter(Article.document_id == article_id)
        .scalar()
    )
    return article_type == 'personal'
