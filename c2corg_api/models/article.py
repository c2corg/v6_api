from sqlalchemy import Column, ForeignKey, Integer

from c2corg_api.models import Base, DBSession, enums, schema
from c2corg_api.models.common import document_types
from c2corg_api.models.document import (
    ArchiveDocument,
    Document,
)
from c2corg_api.models.enums import activity_type, article_category
from c2corg_api.models.utils import ArrayOfEnum, copy_attributes

ARTICLE_TYPE = document_types.ARTICLE_TYPE


class _ArticleMixin:
    categories = Column(ArrayOfEnum(article_category))
    activities = Column(ArrayOfEnum(activity_type))
    article_type = Column(enums.article_type)


attributes = ['categories', 'activities', 'article_type']


class Article(_ArticleMixin, Document):
    __tablename__ = 'articles'

    document_id = Column(
        Integer, ForeignKey(schema + '.documents.document_id'), primary_key=True
    )

    __mapper_args__ = {
        'polymorphic_identity': ARTICLE_TYPE,
        'inherit_condition': Document.document_id == document_id,
    }

    def to_archive(self):
        article = ArchiveArticle()
        super()._to_archive(article)
        copy_attributes(self, article, attributes)

        return article

    def update(self, other):
        super().update(other)
        copy_attributes(other, self, attributes)


class ArchiveArticle(_ArticleMixin, ArchiveDocument):
    __tablename__ = 'articles_archives'

    id = Column(
        Integer, ForeignKey(schema + '.documents_archives.id'), primary_key=True
    )

    __mapper_args__ = {
        'polymorphic_identity': ARTICLE_TYPE,
        'inherit_condition': ArchiveDocument.id == id,
    }

    __table_args__ = Base.__table_args__


def is_personal(article_id):
    article_type = (
        DBSession.query(Article.article_type)
        .select_from(Article.__table__)
        .filter(Article.document_id == article_id)
        .scalar()
    )
    return article_type == 'personal'
