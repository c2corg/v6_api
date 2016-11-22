import logging

import collections
import datetime

from c2corg_api.ext.colander_ext import geojson_from_wkbelement
from c2corg_api.models import DBSession
from c2corg_api.models.document import ArchiveDocument
from c2corg_api.models.document_history import HistoryMetaData, DocumentVersion
from c2corg_api.models.user import AccountNotValidated, User
from c2corg_common.attributes import langs_priority
from colander import null
from pyramid.httpexceptions import HTTPError, HTTPNotFound, HTTPForbidden, \
    HTTPNotModified
from pyramid.view import view_config
from cornice import Errors
from cornice.util import json_error, _JSONError
from cornice.resource import view
from geoalchemy2 import WKBElement
from sqlalchemy.inspection import inspect
from sqlalchemy.sql.expression import over, and_
from sqlalchemy.sql.functions import func

log = logging.getLogger(__name__)

cors_policy = dict(
    headers=('Content-Type'),
    origins=('*')
)


@view_config(context=HTTPNotFound)
@view_config(context=HTTPError)
@view_config(context=HTTPForbidden)
def http_error_handler(exc, request):
    """In case of a HTTP error, return the error details as JSON, e.g.:

        {
            "status": "error",
            "errors": [
                {
                    "location": "body",
                    "name": "Not Found",
                    "description": "document not found"
                }
            ]
        }
    """
    if isinstance(exc, _JSONError):
        # if it is an error from Cornice, just return it
        return exc

    request.errors = Errors(exc.code)
    request.errors.add('body', exc.title, exc.detail)

    return json_error(request)


@view_config(context=Exception)
def catch_all_error_handler(exc, request):
    log.exception('unexpected error')

    show_debugger_for_errors = \
        request.registry.settings.get('show_debugger_for_errors', '')
    if show_debugger_for_errors == 'true':
        raise exc

    request.errors = Errors(500)
    request.errors.add(
        'body', 'unexpected error', 'please consult the server logs')

    return json_error(request)


@view_config(context=AccountNotValidated)
def account_error_handler(exc, request):
    request.errors = Errors(400)
    request.errors.add('body', 'Error', exc.args)

    return json_error(request)


def json_view(**kw):
    """ A Cornice view that expects 'application/json' as content-type.
    """
    kw['content_type'] = 'application/json'
    return view(**kw)


def restricted_json_view(**kw):
    """ A Cornice view that handles restricted json resources.
    """
    if 'permission' not in kw:
        kw['permission'] = 'authenticated'
    return json_view(**kw)


def restricted_view(**kw):
    """ A Cornice view that handles restricted resources.
    """
    if 'permission' not in kw:
        kw['permission'] = 'authenticated'
    return view(**kw)


def to_json_dict(obj, schema, with_special_locales_attrs=False):
    obj_dict = serialize(schema.dictify(obj))

    # manually copy certain attributes that were set on the object (it would be
    # cleaner to add the field to the schema, but ColanderAlchemy doesn't like
    # it because it's not a real column)
    special_attributes = [
        'available_langs', 'associations', 'maps', 'areas', 'author',
        'protected', 'type', 'name', 'forum_username', 'creator'
    ]
    for attr in special_attributes:
        if hasattr(obj, attr):
            obj_dict[attr] = getattr(obj, attr)

    locale_special_attributes = [
        'topic_id'
    ]
    if with_special_locales_attrs and hasattr(obj, 'locales'):
        for i in range(0, len(obj.locales)):
            locale = obj.locales[i]
            locale_dict = obj_dict['locales'][i]
            for attr in locale_special_attributes:
                if hasattr(locale, attr):
                    locale_dict[attr] = getattr(locale, attr)

    return obj_dict


def serialize(data):
    """
    Colanders `serialize` method is not intended for JSON serialization (it
    turns everything into a string and keeps colander.null).
    https://github.com/tisdall/cornice/blob/c18b873/cornice/schemas.py
    Returns the most agnostic version of specified data.
    (remove colander notions, datetimes in ISO, ...)
    """
    if isinstance(data, str):
        return str(data)
    if isinstance(data, collections.Mapping):
        return dict(list(map(serialize, iter(data.items()))))
    if isinstance(data, collections.Iterable):
        return type(data)(list(map(serialize, data)))
    if isinstance(data, (datetime.date, datetime.datetime)):
        return data.isoformat()
    if isinstance(data, WKBElement):
        return geojson_from_wkbelement(data)
    if data is null:
        return None

    return data


def to_seconds(date):
    return int((date - datetime.datetime(1970, 1, 1)).total_seconds())


def set_best_locale(documents, preferred_lang, expunge=True):
    """Sets the "best" locale on the given documents. The "best" locale is
    the locale in the given "preferred language" if available. Otherwise
    it is the "most relevant" translation according to `langs_priority`.
    """
    if preferred_lang is None:
        return

    for document in documents:
        # need to detach the document from the session, so that the
        # following change to `document.locales` is not persisted
        if expunge and not inspect(document).detached:
            DBSession.expunge(document)

        if document.locales:
            available_locales = {
                locale.lang: locale for locale in document.locales}
            best_locale = get_best_locale(available_locales, preferred_lang)
            if best_locale:
                document.locales = [best_locale]


def get_best_locale(available_locales, preferred_lang):
    if preferred_lang in available_locales:
        best_locale = available_locales[preferred_lang]
    else:
        best_locale = next(
                (available_locales[lang] for lang in langs_priority
                 if lang in available_locales), None)
    return best_locale


def set_creator(documents, field_name):
    """Set the creator (the user who created the first version of a document)
    on a list of documents.
    """
    if not documents:
        return
    document_ids = [o.document_id for o in documents]

    author_for_documents = get_creators(document_ids)

    for document in documents:
        setattr(
            document, field_name,
            author_for_documents.get(document.document_id))


def get_creators(document_ids):
    """ Get the creator for the list of given document ids.
    """
    t = DBSession.query(
        ArchiveDocument.document_id.label('document_id'),
        User.id.label('user_id'),
        User.name.label('name'),
        over(
            func.rank(), partition_by=ArchiveDocument.document_id,
            order_by=HistoryMetaData.id).label('rank')). \
        select_from(ArchiveDocument). \
        join(
            DocumentVersion,
            and_(
                ArchiveDocument.document_id == DocumentVersion.document_id,
                ArchiveDocument.version == 1)). \
        join(HistoryMetaData,
             DocumentVersion.history_metadata_id == HistoryMetaData.id). \
        join(User,
             HistoryMetaData.user_id == User.id). \
        filter(ArchiveDocument.document_id.in_(document_ids)). \
        subquery('t')
    query = DBSession.query(
            t.c.document_id, t.c.user_id, t.c.name). \
        filter(t.c.rank == 1)

    return {
        document_id: {
            'name': name,
            'user_id': user_id
        } for document_id, user_id, name in query
    }


def set_author(outings, lang):
    """Set the author (the user who created an outing) on a list of
    outings.
    """
    set_creator(outings, 'author')


def etag_cache(request, key):
    """Use the HTTP Entity Tag cache for Browser side caching
    If a "If-None-Match" header is found, and equivalent to ``key``,
    then a ``304`` HTTP message will be returned with the ETag to tell
    the browser that it should use its current cache of the page.
    Otherwise, the ETag header will be added to the response headers.
    Suggested use is within a view like so:
    .. code-block:: python
        def view(request):
            etag_cache(request, key=1)
            return render('/splash.mako')
    .. note::
        This works because etag_cache will raise an HTTPNotModified
        exception if the ETag received matches the key provided.

    Implementation adapted from:
    https://github.com/Pylons/pylons/blob/799c310/pylons/controllers/util.py#L148  # noqa
    """
    # we are always using a weak ETag validator
    etag = 'W/"%s"' % key
    etag_matcher = request.if_none_match

    if str(key) in etag_matcher:
        headers = [
            ('ETag', etag)
        ]
        log.debug("ETag match, returning 304 HTTP Not Modified Response")
        raise HTTPNotModified(headers=headers)
    else:
        request.response.headers['ETag'] = etag
        log.debug("ETag didn't match, returning response object")
