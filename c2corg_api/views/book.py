import functools

from c2corg_api.models.book import (
    Book,
    schema_book,
    schema_create_book,
    schema_update_book,
    BOOK_TYPE, ArchiveBook)
from c2corg_api.models.document import ArchiveDocumentLocale
from c2corg_api.views.document_info import DocumentInfoRest
from c2corg_api.views.document_version import DocumentVersionRest
from c2corg_common.fields_book import fields_book
from cornice.resource import resource, view

from c2corg_api.views.document_schemas import book_documents_config
from c2corg_api.views.document import DocumentRest, make_validator_create, \
    make_validator_update
from c2corg_api.views import cors_policy, restricted_json_view
from c2corg_api.views.validation import validate_id, validate_pagination, \
    validate_lang_param, validate_preferred_lang_param, \
    validate_associations, validate_lang, validate_version_id

validate_book_create = make_validator_create(fields_book.get('required'))
validate_book_update = make_validator_update(fields_book.get('required'))
validate_associations_create = functools.partial(
    validate_associations, BOOK_TYPE, True)
validate_associations_update = functools.partial(
    validate_associations, BOOK_TYPE, False)


@resource(collection_path='/books', path='/books/{id}',
          cors_policy=cors_policy)
class BookRest(DocumentRest):

    @view(validators=[validate_pagination, validate_preferred_lang_param])
    def collection_get(self):
        return self._collection_get(BOOK_TYPE, book_documents_config)

    @view(validators=[validate_id, validate_lang_param])
    def get(self):
        return self._get(Book, schema_book, include_areas=False)

    @restricted_json_view(
            schema=schema_create_book,
            validators=[validate_book_create,
                        validate_associations_create])
    def collection_post(self):
        return self._collection_post(schema_book)

    @restricted_json_view(
            schema=schema_update_book,
            validators=[validate_id,
                        validate_book_update,
                        validate_associations_update])
    def put(self):
        return self._put(Book, schema_book)


@resource(path='/books/{id}/{lang}/{version_id}',
          cors_policy=cors_policy)
class BooksVersionRest(DocumentVersionRest):
    @view(validators=[validate_id, validate_lang, validate_version_id])
    def get(self):
        return self._get_version(
            ArchiveBook, ArchiveDocumentLocale, schema_book)


@resource(path='/books/{id}/{lang}/info', cors_policy=cors_policy)
class BooksInfoRest(DocumentInfoRest):
    @view(validators=[validate_id, validate_lang])
    def get(self):
        return self._get_document_info(Book)
