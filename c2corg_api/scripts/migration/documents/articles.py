from c2corg_api.models.article import Article, ArchiveArticle, ARTICLE_TYPE
from c2corg_api.models.document import DocumentLocale, ArchiveDocumentLocale, \
    DOCUMENT_TYPE
from c2corg_api.scripts.migration.documents.document import MigrateDocuments, \
    DEFAULT_QUALITY
from c2corg_api.scripts.migration.documents.routes import MigrateRoutes


class MigrateArticles(MigrateDocuments):

    def get_name(self):
        return 'articles'

    def get_model_document(self, locales):
        return DocumentLocale if locales else Article

    def get_model_archive_document(self, locales):
        return ArchiveDocumentLocale if locales else ArchiveArticle

    def get_count_query(self):
        return (
            ' select count(*) '
            ' from app_articles_archives aa join articles t on aa.id = t.id '
            ' where t.redirects_to is null;'
        )

    def get_query(self):
        return (
            ' select '
            '   aa.id, aa.document_archive_id, aa.is_latest_version, '
            '   aa.is_protected, aa.redirects_to, '
            '   aa.elevation, aa.categories, aa.activities, aa.article_type '
            ' from app_articles_archives aa join articles t on aa.id = t.id '
            ' where t.redirects_to is null '
            ' order by aa.id, aa.document_archive_id;'
        )

    def get_count_query_locales(self):
        return (
            ' select count(*) '
            ' from app_articles_i18n_archives aa '
            '   join articles t on aa.id = t.id '
            ' where t.redirects_to is null;'
        )

    def get_query_locales(self):
        return (
            ' select '
            '    aa.id, aa.document_i18n_archive_id, aa.is_latest_version, '
            '    aa.culture, aa.name, aa.description '
            ' from app_articles_i18n_archives aa '
            '   join articles t on aa.id = t.id '
            ' where t.redirects_to is null '
            ' order by aa.id, aa.culture, aa.document_i18n_archive_id;'
        )

    def get_document(self, document_in, version):
        categories = self.convert_types(
            document_in.categories, MigrateArticles.article_categories)
        if 'draft' in categories:
            default_quality = 'draft'
            categories.remove('draft')
        else:
            default_quality = DEFAULT_QUALITY
        return dict(
            document_id=document_in.id,
            type=ARTICLE_TYPE,
            version=version,

            quality=default_quality,
            categories=categories,
            activities=self.convert_types(
                document_in.activities, MigrateRoutes.activities),
            article_type=self.convert_type(
                document_in.article_type, MigrateArticles.article_types)
        )

    def get_document_locale(self, document_in, version):
        description = self.convert_tags(document_in.description)
        description, summary = self.extract_summary(description)
        return dict(
            document_id=document_in.id,
            id=document_in.document_i18n_archive_id,
            type=DOCUMENT_TYPE,
            version=version,
            lang=document_in.culture,
            title=document_in.name,
            description=description,
            summary=summary
        )

    article_types = {
        '1': 'collab',
        '2': 'personal'
    }

    article_categories = {
        '1': 'mountain_environment',
        '2': 'gear',
        '11': 'technical',
        '4': 'topoguide_supplements',
        '7': 'soft_mobility',
        '8': 'expeditions',
        '3': 'stories',
        '9': 'c2c_meetings',
        '10': 'tags',
        '5': 'site_info',
        '6': 'association',
        '100': None
    }
