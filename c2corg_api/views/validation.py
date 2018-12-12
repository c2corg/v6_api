import functools

from c2corg_api.models import DBSession, article, image
from c2corg_api.models.area import AREA_TYPE
from c2corg_api.models.association import Association, \
    updatable_associations, association_keys
from c2corg_api.models.book import BOOK_TYPE
from c2corg_api.models.document import Document
from c2corg_api.models.article import ARTICLE_TYPE
from c2corg_api.models.document_history import has_been_created_by
from c2corg_api.models.image import IMAGE_TYPE
from c2corg_api.models.outing import OUTING_TYPE
from c2corg_api.models.user import User
from c2corg_api.models.xreport import XREPORT_TYPE
from c2corg_api.models.route import ROUTE_TYPE
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.models.waypoint import WAYPOINT_TYPE
from c2corg_api.views.document_associations import get_first_column

from c2corg_common.associations import valid_associations
from c2corg_common.attributes import default_langs
from c2corg_common import document_types
from colander import null
from cornice.errors import Errors
from pyramid.httpexceptions import HTTPBadRequest
from sqlalchemy.sql.expression import exists, and_
from webob.descriptors import parse_int_safe
from dateutil import parser as datetime_parser
import urllib


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


def validate_cook_(cook, request):
    """Checks if a given cooking lang is one of the available langs.
    """
    if cook is not None:
        if cook in default_langs:
            request.validated['cook'] = cook
        else:
            request.errors.add('querystring', 'cook', 'invalid lang')


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


def validate_cook_param(request, **kwargs):
    """Checks if the cooking language given in the url as GET parameter
    is correct ("...?cook=...").
    """
    cook = request.GET.get('cook')
    validate_cook_(cook, request)


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


def validate_simple_token_pagination(request, **kwargs):
    """
    Validate token pagination parameters (limit and token) for changes feed.
    """
    check_get_for_integer_property(request, 'limit', False)
    validate_simple_token(request)


def validate_user_id(request, **kwargs):
    """
    Checks for a required user id parameter.
    """
    check_get_for_integer_property(request, 'u', True)


def validate_user_id_not_required(request, **kwargs):
    """
    Checks for a non-required user id parameter.
    """
    check_get_for_integer_property(request, 'u', False)


def parse_datetime(time_raw):
    if time_raw is None or time_raw == '':
        return None
    try:
        time_raw = urllib.parse.unquote(time_raw)
        return datetime_parser.parse(time_raw)
    except ValueError:
        return None


def validate_body_user_id(request, **kwargs):
    """ Check that the user exists.
    """
    user_id = request.validated['user_id']
    user_exists_query = DBSession.query(User). \
        filter(User.id == user_id). \
        exists()
    user_exists = DBSession.query(user_exists_query).scalar()

    if not user_exists:
        request.errors.add(
            'body', 'user_id', 'user {0} does not exist'.format(user_id))


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


def validate_simple_token(request, **kwargs):
    if request.GET.get('token'):
        token = request.GET.get('token')

        # the token should have the format '{id}'
        id = parse_int_safe(token)
        if id is not None:
            request.validated['token_id'] = id
            return
        request.errors.add('querystring', 'token', 'invalid format')


def validate_association_permission(
    request, parent_document_id, parent_document_type, child_document_id,
    child_document_type, raise_exc=False, skip_outing_check=False):
    if request.has_permission('moderator'):
        # moderators can do everything
        return

    # check association with outing (creator or participant)
    # skip when creating an outing (the participant associations do not
    # exist yet at that point).
    if not skip_outing_check and \
            OUTING_TYPE in (parent_document_type, child_document_type):
        validate_outing_association(
            request, parent_document_id, parent_document_type,
            child_document_id, child_document_type, raise_exc)

    # check association with personal image (creator)
    if IMAGE_TYPE in (parent_document_type, child_document_type):
        validate_image_association(
            request, parent_document_id, parent_document_type,
            child_document_id, child_document_type, raise_exc)

    # check association with personal article (creator)
    if ARTICLE_TYPE in (parent_document_type, child_document_type):
        validate_article_association(
            request, parent_document_id, parent_document_type,
            child_document_id, child_document_type, raise_exc)

    # check association with report (creator)
    if XREPORT_TYPE in (parent_document_type, child_document_type):
        validate_xreport_association(
            request, parent_document_id, parent_document_type,
            child_document_id, child_document_type, raise_exc)


def validate_outing_association(
    request, parent_document_id, parent_document_type, child_document_id,
    child_document_type, raise_exc):
    """ If the given association is an association with an outing, this
    function checks if the authenticated user is allowed to change the
    associations with the outing (either moderator or participant).
    """
    if parent_document_type != OUTING_TYPE and \
            child_document_type != OUTING_TYPE:
        # no association with an outing, nothing to check
        return

    if parent_document_type == OUTING_TYPE:
        outing_id = parent_document_id
    else:
        outing_id = child_document_id

    if not has_permission_for_outing(request, outing_id):
        msg = 'no rights to modify associations with outing {}'.format(
            outing_id)
        if raise_exc:
            raise HTTPBadRequest(msg)
        else:
            request.errors.add('body', 'associations.outings', msg)


def validate_article_association(
    request, parent_document_id, parent_document_type, child_document_id,
    child_document_type, raise_exc):
    validate_personal_association(
        request, parent_document_id, parent_document_type, child_document_id,
        child_document_type, raise_exc, ARTICLE_TYPE, article.is_personal,
        'article')


def validate_image_association(
    request, parent_document_id, parent_document_type, child_document_id,
    child_document_type, raise_exc):
    validate_personal_association(
        request, parent_document_id, parent_document_type, child_document_id,
        child_document_type, raise_exc, IMAGE_TYPE, image.is_personal, 'image')


def validate_xreport_association(
    request, parent_document_id, parent_document_type, child_document_id,
    child_document_type, raise_exc):
    validate_personal_association(
        request, parent_document_id, parent_document_type, child_document_id,
        child_document_type, raise_exc, XREPORT_TYPE, lambda _: True,
        'xreport')


def validate_personal_association(
    request, parent_document_id, parent_document_type, child_document_id,
    child_document_type, raise_exc, doc_type, is_personal, label):
    document_ids = set()
    if parent_document_type == doc_type:
        document_ids.add(parent_document_id)
    if child_document_type == doc_type:
        document_ids.add(child_document_id)

    for document_id in document_ids:
        if is_personal(document_id) and not has_been_created_by(
            document_id, request.authenticated_userid) and not \
            is_associated_user(document_id, request.authenticated_userid):
            msg = 'no rights to modify associations with {} {}'.format(
                label, document_id)
            if raise_exc:
                raise HTTPBadRequest(msg)
            else:
                request.errors.add(
                    'body', 'associations.{}s'.format(label), msg)


def has_permission_for_outing(request, outing_id):
    """Check if the user with the given id has permission to change an
    outing. That is only users that are currently assigned to the outing
    can modify it.
    """
    if request.has_permission('moderator'):
        # moderators can change everything
        return True

    user_id = request.authenticated_userid
    return DBSession.query(exists().where(
        and_(
            Association.parent_document_id == user_id,
            Association.child_document_id == outing_id
        ))).scalar()


def check_permission_for_association(
    request, association, skip_outing_check=False):
    validate_association_permission(
        request, association.parent_document_id,
        association.parent_document_type, association.child_document_id,
        association.child_document_type, raise_exc=True,
        skip_outing_check=skip_outing_check)


def association_permission_checker(request, skip_outing_check=False):
    def check(association):
        check_permission_for_association(
            request, association, skip_outing_check)

    return check


def association_permission_removal_checker(request):
    return functools.partial(check_permission_for_association_removal, request)


def check_permission_for_association_removal(request, association):
    if request.has_permission('moderator'):
        # moderators can change everything
        return

    valid_parent = _check_permission_association_doc(
        request,
        association.parent_document_type, association.parent_document_id)
    valid_child = _check_permission_association_doc(
        request,
        association.child_document_type, association.child_document_id)

    if not valid_parent and not valid_child:
        raise HTTPBadRequest(
            'no rights to modify associations between document '
            '{} ({}) and {} ({})'.format(
                association.parent_document_type,
                association.parent_document_id,
                association.child_document_type,
                association.child_document_id))


def _check_permission_association_doc(request, doc_type, document_id):
    if doc_type == OUTING_TYPE:
        if has_permission_for_outing(request, document_id):
            return True
    elif doc_type == IMAGE_TYPE:
        if image.is_personal(document_id) and has_been_created_by(
            document_id, request.authenticated_userid):
            return True
    elif doc_type == ARTICLE_TYPE:
        if article.is_personal(document_id) and has_been_created_by(
            document_id, request.authenticated_userid):
            return True
    elif doc_type == XREPORT_TYPE:
        if (has_been_created_by(document_id, request.authenticated_userid) or
                is_associated_user(document_id, request.authenticated_userid)):
            return True

    return False


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
    _add_associations(associations, associations_in, document_type,
                      'xreports', XREPORT_TYPE, new_errors)

    if new_errors:
        errors.extend(new_errors)
        return None

    _check_for_valid_documents_ids(associations, new_errors)

    if new_errors:
        errors.extend(new_errors)
        return None
    else:
        return associations


def get_associated_user_ids(xreport_id):
    associated_user_ids = get_first_column(
        DBSession.query(User.id).
            join(Association, Association.parent_document_id == User.id).
            filter(Association.child_document_id == xreport_id).
            group_by(User.id).
            all())
    return associated_user_ids


def is_associated_user(xreport_id, user_id):
    """ Required to check if an associated user is able to edit Xreport.
    """
    associated_user_ids = get_associated_user_ids(xreport_id)
    if user_id in associated_user_ids:
        return True


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
            filter(Document.document_id.in_(linked_documents_id)). \
            filter(Document.redirects_to.is_(None))
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
                    'document "{0:n}" does not exist or is redirected'.format(
                        document_id))
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
            if document_key == 'waypoints' and main_document_type != BOOK_TYPE:
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
