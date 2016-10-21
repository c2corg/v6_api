from c2corg_api.models import DBSession
from c2corg_api.models.area import AREA_TYPE
from c2corg_api.models.book import BOOK_TYPE
from c2corg_api.models.document import Document
from c2corg_api.models.article import ARTICLE_TYPE
from c2corg_api.models.image import IMAGE_TYPE
from c2corg_api.models.outing import OUTING_TYPE
from c2corg_api.models.route import ROUTE_TYPE
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.models.waypoint import WAYPOINT_TYPE
from c2corg_common.associations import valid_associations
from c2corg_common.attributes import default_langs
from c2corg_common import document_types
from colander import null
from cornice.errors import Errors
from webob.descriptors import parse_int_safe
from dateutil import parser as datetime_parser


# Validation functions


def create_int_validator(field):
    def validator(request, **kwargs):
        try:
            val = int(request.matchdict[field])
            if val < 0:
                raise ValueError
            request.validated[field] = val
        except ValueError:
            request.errors.add('querystring', field, 'invalid ' + field)
    return validator

validate_id = create_int_validator('id')
validate_version_id = create_int_validator('version_id')


def validate_lang_(lang, request):
    """Checks if a given lang is one of the available langs.
    """
    if lang is not None:
        if lang in default_langs:
            request.validated['lang'] = lang
        else:
            request.errors.add('querystring', 'lang', 'invalid lang')


def validate_lang(request, **kwargs):
    """Checks if the language given in the url as match-parameter
    is correct (".../{lang}").
    """
    lang = request.matchdict['lang']
    validate_lang_(lang, request)


def validate_document_type(request, **kwargs):
    """Checks if the document type given in the url as match-parameter
    is correct (".../{doc_type}").
    """
    doc_type = request.matchdict['doc_type']
    if doc_type is not None:
        if doc_type in document_types.ALL:
            request.validated['doc_type'] = doc_type
            return
    request.errors.add('querystring', 'doc_type', 'invalid doc_type')


def validate_lang_param(request, **kwargs):
    """Checks if the language given in the url as GET parameter
    is correct ("...?l=...").
    """
    lang = request.GET.get('l')
    validate_lang_(lang, request)


def validate_preferred_lang_param(request, **kwargs):
    """Checks if the preferred language given in the url as GET parameter
    is correct ("...?pl=...").
    """
    lang = request.GET.get('pl')
    validate_lang_(lang, request)


def is_missing(val):
    return val is None or val == '' or val == [] or val is null


def check_required_fields(document, fields, request, updating):
    """Checks that the given fields are set on the document.
    """

    for field in fields:
        if '.' not in field:
            if updating and field in ['geometry', 'locales']:
                # when updating geometry and locales may be empty
                continue
            if is_missing(document.get(field)):
                request.errors.add('body', field, 'Required')
        else:
            # fields like 'geometry.geom'
            if field in ['locales.title']:
                # this is a required field for all documents, which is already
                # checked when validating against the Colander schema
                pass
            else:
                field_parts = field.split('.')
                attr = document.get(field_parts[0])
                if attr:
                    if is_missing(attr.get(field_parts[1])):
                        request.errors.add('body', field, 'Required')


def check_duplicate_locales(document, request):
    """Check that there is only one entry for each lang.
    """
    locales = document.get('locales')
    if locales:
        langs = set()
        for locale in locales:
            lang = locale.get('lang')
            if lang in langs:
                request.errors.add(
                    'body', 'locales',
                    'lang "%s" is given twice' % (lang))
                return
            langs.add(lang)


def check_get_for_integer_property(request, key, required):
    """Checks if the value associated to a given key is an integer.
    """
    if not required and request.GET.get(key) is None:
        return

    try:
        request.validated[key] = int(request.GET.get(key))
    except:
        request.errors.add('querystring', key, 'invalid ' + key)


def validate_pagination(request, **kwargs):
    """
    Checks if a given optional offset is an integer and
    if a given optional limit is an integer.
    """
    check_get_for_integer_property(request, 'offset', False)
    check_get_for_integer_property(request, 'limit', False)


def validate_token_pagination(request, **kwargs):
    """
    Validate token pagination parameters (limit and token) for feed.
    """
    check_get_for_integer_property(request, 'limit', False)
    validate_token(request)


def validate_user_id(request, **kwargs):
    """
    Checks for a required user id parameter.
    """
    check_get_for_integer_property(request, 'u', True)


def parse_datetime(time_raw):
    if time_raw is None or time_raw == '':
        return None
    try:
        return datetime_parser.parse(time_raw)
    except ValueError:
        return None


def validate_token(request, **kwargs):
    if request.GET.get('token'):
        token = request.GET.get('token')

        # the token should have the format '{id},{datetime in isoformat}'
        if ',' in token:
            token_parts = token.split(',')

            if len(token_parts) == 2:
                id = parse_int_safe(token_parts[0])
                time = parse_datetime(token_parts[1])

                if id is not None and time:
                    # everything ok
                    request.validated['token_id'] = id
                    request.validated['token_time'] = time
                    return
        request.errors.add('querystring', 'token', 'invalid format')


def validate_required_json_string(key, request):
    """Checks if a given key is present in the request.
    """

    value = None
    if key in request.json:
        value = request.json[key]
    else:
        request.errors.add('body', key, 'Required')
        return

    if isinstance(value, str):
        request.validated[key] = value
    else:
        request.errors.add('body', key, 'Invalid')


def validate_associations(document_type, is_on_create, request, **kwargs):
    if is_on_create:
        associations_in = request.validated.get('associations', None)
    else:
        associations_in = request.validated. \
            get('document', {}).get('associations', None)

    if not associations_in:
        return

    request.validated['associations'] = validate_associations_in(
        associations_in, document_type, request.errors)


def validate_associations_in(associations_in, document_type, errors):
    """Validate the provided associations:

        - Check that the linked documents exist.
        - Check that the linked documents have the right document type (e.g. a
          document listed as route association must really be a route).
        - Check that only valid association combinations are given.

    Returns the validated associations.
    """
    new_errors = Errors()
    associations = {}

    _add_associations(associations, associations_in, document_type,
                      'users', USERPROFILE_TYPE, new_errors)
    _add_associations(associations, associations_in, document_type,
                      'routes', ROUTE_TYPE, new_errors)
    _add_associations(associations, associations_in, document_type,
                      'waypoints', WAYPOINT_TYPE, new_errors)
    _add_associations(associations, associations_in, document_type,
                      'images', IMAGE_TYPE, new_errors)
    _add_associations(associations, associations_in, document_type,
                      'articles', ARTICLE_TYPE, new_errors)
    _add_associations(associations, associations_in, document_type,
                      'waypoint_children', WAYPOINT_TYPE, new_errors)
    _add_associations(associations, associations_in, document_type,
                      'areas', AREA_TYPE, new_errors)
    _add_associations(associations, associations_in, document_type,
                      'outings', OUTING_TYPE, new_errors)
    _add_associations(associations, associations_in, document_type,
                      'books', BOOK_TYPE, new_errors)

    if new_errors:
        errors.extend(new_errors)
        return None

    _check_for_valid_documents_ids(associations, new_errors)

    if new_errors:
        errors.extend(new_errors)
        return None
    else:
        return associations


def _check_for_valid_documents_ids(associations, errors):
    """ Check that the given documents do exists and that they are of the
    correct type (e.g. a document listed as route association must really be
    a route).
    """
    linked_documents_id = _get_linked_document_ids(associations)

    # load the type for each linked document
    if linked_documents_id:
        query_documents_with_type = DBSession. \
            query(Document.document_id, Document.type). \
            filter(Document.document_id.in_(linked_documents_id))
        type_for_document_id = {
            str(document_id): doc_type
            for document_id, doc_type in query_documents_with_type
        }
    else:
        type_for_document_id = {}

    for document_key, docs in associations.items():
        doc_type = association_keys[document_key]
        for doc in docs:
            document_id = doc['document_id']
            if str(document_id) not in type_for_document_id:
                errors.add(
                    'body', 'associations.' + document_key,
                    'document "{0:n}" does not exist'.format(document_id))
                continue
            if doc_type != type_for_document_id[str(document_id)]:
                errors.add(
                    'body', 'associations.' + document_key,
                    'document "{0:n}" is not of type "{1}"'.format(
                        document_id, doc_type))


def _get_linked_document_ids(associations):
    """ Get a list of document ids of all linked documents.
    """
    return set().union(*[
        [
            doc['document_id'] for doc in docs
        ] for docs in associations.values()
    ])


def _add_associations(
        associations, associations_in, main_document_type,
        document_key, other_document_type, errors):
    valid_types = updatable_associations.get(main_document_type, set())

    if document_key not in valid_types:
        return

    associations_for_type = associations_in.get(document_key, None)
    # skip if no associations are provided for this type. but if an empty list
    # is given, create an entry (all existing associations of that type
    # should be removed).
    if associations_for_type is not None:
        is_parent = _is_parent_of_association(
            main_document_type, other_document_type)

        if is_parent is None:
            errors.add(
                'body', 'associations.' + document_key,
                'invalid association type')
        else:
            if document_key == 'waypoints':
                is_parent = True
            elif document_key == 'waypoint_children':
                is_parent = False

            associations[document_key] = [
                {
                    'document_id': doc['document_id'],
                    'is_parent': is_parent
                } for doc in associations_in[document_key]
            ]


def _is_parent_of_association(main_document_type, other_document_type):
    if (main_document_type, other_document_type) in valid_associations:
        return False
    elif (other_document_type, main_document_type) in valid_associations:
        return True
    else:
        return None

association_keys = {
    'routes': ROUTE_TYPE,
    'waypoints': WAYPOINT_TYPE,
    'waypoint_children': WAYPOINT_TYPE,
    'users': USERPROFILE_TYPE,
    'images': IMAGE_TYPE,
    'articles': ARTICLE_TYPE,
    'areas': AREA_TYPE,
    'books': BOOK_TYPE,
    'outings': OUTING_TYPE
}

association_keys_for_types = {
    ROUTE_TYPE: 'routes',
    WAYPOINT_TYPE: 'waypoints',
    USERPROFILE_TYPE: 'users',
    ARTICLE_TYPE: 'articles',
    BOOK_TYPE: 'books',
    IMAGE_TYPE: 'images',
    AREA_TYPE: 'areas',
    OUTING_TYPE: 'outings'
}

# associations that can be updated/created when updating/creating a document
# e.g. when creating a route, route and waypoint associations can be created
updatable_associations = {
    ROUTE_TYPE: {'articles', 'routes', 'waypoints', 'books'},
    WAYPOINT_TYPE: {'articles', 'waypoints', 'waypoint_children'},
    OUTING_TYPE: {'articles', 'routes', 'users', 'waypoints'},
    IMAGE_TYPE: {'routes', 'waypoints', 'images', 'users', 'articles',
                 'areas', 'outings', 'books'},
    ARTICLE_TYPE: {'articles', 'images', 'users', 'routes', 'waypoints',
                   'outings', 'books'},
    AREA_TYPE: {'images'},
    BOOK_TYPE: {'routes', 'articles', 'images', 'waypoints'}
}
