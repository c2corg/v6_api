import functools

from c2corg_api.models.book import BOOK_TYPE, ArchiveBook, Book
from c2corg_api.models.common.fields_book import fields_book
from c2corg_api.models.document import ArchiveDocumentLocale
from c2corg_api.schemas.base import body_validator
from c2corg_api.schemas.book import BookCreateSchema, BookUpdateSchema, book_schema
from c2corg_api.views import restricted_json_view
from c2corg_api.views.document import (
    collection_get,
    create_document,
    make_validator_create,
    make_validator_update,
    put_document,
    read_document,
)
from c2corg_api.views.document_info import document_info
from c2corg_api.views.document_schemas import book_documents_config
from c2corg_api.views.document_version import document_version
from c2corg_api.views.resource import view
from c2corg_api.views.validation import (
    validate_associations,
    validate_cook_param,
    validate_id,
    validate_lang,
    validate_lang_param,
    validate_pagination,
    validate_preferred_lang_param,
    validate_version_id,
)

validate_book_create = make_validator_create(fields_book.get('required'))
validate_book_update = make_validator_update(fields_book.get('required'))
validate_associations_create = functools.partial(validate_associations, BOOK_TYPE, True)
validate_associations_update = functools.partial(
    validate_associations, BOOK_TYPE, False
)


@restricted_json_view(
    validators=[
        body_validator(BookCreateSchema),
        validate_book_create,
        validate_associations_create,
    ],
)
def create_book(request):
    return create_document(request, book_schema)


@restricted_json_view(
    validators=[
        body_validator(BookUpdateSchema),
        validate_id,
        validate_book_update,
        validate_associations_update,
    ],
)
def update_book(request):
    return put_document(request, Book, book_schema)


@view(validators=[validate_pagination, validate_preferred_lang_param])
def list_books(request):
    return collection_get(request, BOOK_TYPE, book_documents_config)


@view(validators=[validate_id, validate_lang_param, validate_cook_param])
def get_book(request):
    return read_document(
        request, book_documents_config, book_schema, include_areas=False
    )


@view(validators=[validate_id, validate_lang, validate_version_id])
def get_book_version(request):
    return document_version(
        request, ArchiveBook, BOOK_TYPE, ArchiveDocumentLocale, book_schema
    )


@view(validators=[validate_id, validate_lang])
def get_book_info(request):
    return document_info(request, book_documents_config)
