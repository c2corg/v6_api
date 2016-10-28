from c2corg_api.models.book import Book, ArchiveBook, BOOK_TYPE
from c2corg_api.models.document import DocumentLocale, ArchiveDocumentLocale, \
    DOCUMENT_TYPE
from c2corg_api.scripts.migration.documents.document import MigrateDocuments, \
  DEFAULT_QUALITY
from c2corg_api.scripts.migration.documents.routes import MigrateRoutes


class MigrateBooks(MigrateDocuments):

    def get_name(self):
        return 'books'

    def get_model_document(self, locales):
        return DocumentLocale if locales else Book

    def get_model_archive_document(self, locales):
        return ArchiveDocumentLocale if locales else ArchiveBook

    def get_count_query(self):
        return (
            ' select count(*) '
            ' from app_books_archives ba join books b on ba.id = b.id '
            ' where '
            ' b.redirects_to is null; '
        )

    def get_query(self):
        return (
            ' select '
            '   ba.id, ba.document_archive_id, ba.is_latest_version, '
            '   ba.is_protected, ba.redirects_to, '
            '   ba.activities, ba.book_types, '
            '   ba.author, ba.editor, ba.url, ba.isbn, ba.langs, '
            '   ba.nb_pages, ba.publication_date '
            ' from app_books_archives ba join books b on ba.id = b.id '
            ' where b.redirects_to is null '
            ' order by ba.id, ba.document_archive_id;'
        )

    def get_count_query_locales(self):
        return (
            ' select count(*) '
            ' from app_books_i18n_archives ba '
            '   join books b on ba.id = b.id '
            ' where b.redirects_to is null;'
        )

    def get_query_locales(self):
        return (
            ' select '
            '    ba.id, ba.document_i18n_archive_id, ba.is_latest_version, '
            '    ba.culture, ba.name, ba.description '
            ' from app_books_i18n_archives ba '
            '   join books b on ba.id = b.id '
            ' where b.redirects_to is null '
            ' order by ba.id, ba.culture, ba.document_i18n_archive_id;'
        )

    def get_document(self, document_in, version):
        if document_in.langs and 'ot' in document_in.langs:
            document_in.langs.remove('ot')
            document_in.langs.append('it')
        return dict(
            document_id=document_in.id,
            type=BOOK_TYPE,
            version=version,

            activities=self.convert_types(
                document_in.activities, MigrateRoutes.activities),
            book_types=self.convert_types(
                document_in.book_types, MigrateBooks.book_types),
            author=document_in.author,
            editor=document_in.editor,
            url=document_in.url,
            isbn=document_in.isbn,
            nb_pages=document_in.nb_pages,
            publication_date=document_in.publication_date,
            langs=document_in.langs,
            quality=DEFAULT_QUALITY
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

    book_types = {
        '1': 'topo',
        '2': 'environment',
        '4': 'historical',
        '16': 'biography',
        '6': 'photos-art',
        '8': 'novel',
        '10': 'technics',
        '14': 'tourism',
        '18': 'magazine',
    }
