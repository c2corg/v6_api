import logging

from sqlalchemy import func

from c2corg_api import DBSession
from c2corg_api.httpexceptions import HTTPBadRequest, HTTPNotFound
from c2corg_api.models.document import Document, DocumentLocale
from c2corg_api.models.favourite import (
    FAVOURITE_TYPES,
    Favourite,
    FavouriteFolder,
    FavouriteLog,
)
from c2corg_api.models.route import ROUTE_TYPE, RouteLocale
from c2corg_api.models.user import User
from c2corg_api.schemas.base import Schema, body_validator
from c2corg_api.schemas.types import Int, Seq, Str
from c2corg_api.search.notify_sync import notify_es_syncer
from c2corg_api.views import get_best_locale
from c2corg_api.views.resource import write
from c2corg_api.views.validation import validate_id

log = logging.getLogger(__name__)

FOLDER_NAME_MAX_LENGTH = 100


class FavouriteSchema(Schema):
    document_id: Int
    # the folder to put the favourite in; none: unchanged (the main list
    # for a new favourite)
    folder_id: Int = None


class MoveFavouriteSchema(Schema):
    document_id: Int
    # none: back to the main list
    folder_id: Int = None


class FolderSchema(Schema):
    name: Str(max_length=FOLDER_NAME_MAX_LENGTH, min_length=1)


class FolderOrderSchema(Schema):
    folder_ids: Seq(Int)


def get_favourite(user_id, document_id):
    """Return the favourite of a user for a document, or None."""
    return (
        DBSession.query(Favourite)
        .filter(Favourite.user_id == user_id)
        .filter(Favourite.document_id == document_id)
        .first()
    )


def validate_document(request, **kwargs):
    """Check that the document exists, can be a favourite and is not merged."""
    # a deleted document is no longer in the documents table (see
    # views.document_trash)
    document_id = request.validated.get('document_id')
    if document_id is None:
        return
    document_type = (
        DBSession.query(Document.type)
        .filter(Document.document_id == document_id)
        .filter(Document.type.in_(FAVOURITE_TYPES))
        .filter(Document.redirects_to.is_(None))
        .scalar()
    )
    if document_type is None:
        request.errors.add(
            'body', 'document_id', f'document {document_id} does not exist'
        )
    else:
        request.validated['document_type'] = document_type


def validate_folder(request, **kwargs):
    """Check that the folder of the body, if any, is one of the user's."""
    folder_id = request.validated.get('folder_id')
    if folder_id is None:
        return
    if _get_folder(request.authenticated_userid, folder_id) is None:
        request.errors.add('body', 'folder_id', f'folder {folder_id} does not exist')


def _get_folder(user_id, folder_id):
    return (
        DBSession.query(FavouriteFolder)
        .filter(FavouriteFolder.id == folder_id)
        .filter(FavouriteFolder.user_id == user_id)
        .first()
    )


def _notify_if_route(request, document_type):
    # only the routes have their favourites in the search index (field `u`)
    if document_type == ROUTE_TYPE:
        notify_es_syncer(request.registry.queue_config)


@write(
    validators=[body_validator(FavouriteSchema), validate_document, validate_folder],
    permission='authenticated',
    json=True,
)
def add_favourite(request):
    """Add a document to the favourites of the authenticated user.

    Nothing changes if it is one already, except its folder if one is given.

    Request:
        `POST` `/favourites/add` (or `/tags/add`)

    Request body:
        {'document_id': @document_id@, 'folder_id': @folder_id@ (optional)}
    """
    document_id = request.validated['document_id']
    document_type = request.validated['document_type']
    folder_id = request.validated.get('folder_id')
    user_id = request.authenticated_userid

    favourite = get_favourite(user_id, document_id)
    if favourite is not None:
        if folder_id is not None:
            favourite.folder_id = folder_id
        return {}

    DBSession.add(
        Favourite(
            user_id=user_id,
            document_id=document_id,
            document_type=document_type,
            folder_id=folder_id,
        )
    )
    DBSession.add(
        FavouriteLog(
            user_id=user_id,
            document_id=document_id,
            document_type=document_type,
            is_creation=True,
        )
    )
    _notify_if_route(request, document_type)
    return {}


@write(
    validators=[body_validator(FavouriteSchema), validate_document],
    permission='authenticated',
    json=True,
)
def remove_favourite(request):
    """Remove a document from the favourites of the authenticated user.

    Nothing changes if it is not one.

    Request:
        `POST` `/favourites/remove` (or `/tags/remove`)

    Request body:
        {'document_id': @document_id@}
    """
    document_id = request.validated['document_id']
    user_id = request.authenticated_userid
    favourite = get_favourite(user_id, document_id)
    if favourite is None:
        return {}

    document_type = favourite.document_type
    DBSession.delete(favourite)
    DBSession.add(
        FavouriteLog(
            user_id=user_id,
            document_id=document_id,
            document_type=document_type,
            is_creation=False,
        )
    )
    _notify_if_route(request, document_type)
    return {}


@write(
    validators=[
        body_validator(MoveFavouriteSchema),
        validate_document,
        validate_folder,
    ],
    permission='authenticated',
    json=True,
)
def move_favourite(request):
    """Put a favourite in a folder of the user, or back in the main list.

    Request:
        `POST` `/favourites/move`

    Request body:
        {'document_id': @document_id@, 'folder_id': @folder_id@ or null}
    """
    favourite = get_favourite(
        request.authenticated_userid, request.validated['document_id']
    )
    if favourite is None:
        raise HTTPBadRequest('This document is not a favourite.')
    favourite.folder_id = request.validated.get('folder_id')
    return {}


def read_favourite(request):
    """Tell whether the authenticated user has a document in favourites.

    Request:
        `GET` `/favourites/has/{document_id}`

    Example response:

        {'favourite': true, 'folder_id': 12}
    """
    favourite = get_favourite(
        request.authenticated_userid, request.validated['document_id']
    )
    return {
        'favourite': favourite is not None,
        'folder_id': favourite.folder_id if favourite is not None else None,
    }


def read_todo_tag(request):
    """Tell whether the authenticated user tagged a document as todo.

    The former name of the favourites, for the clients not updated yet.

    Request:
        `GET` `/tags/has/{document_id}`

    Example response:

        {'todo': true}
    """
    return {'todo': read_favourite(request)['favourite']}


def read_favourites(request):
    """List the favourites and the folders of the authenticated user.

    The favourites, latest first, with the title of the document in the
    language `pl`, else in the best other one.

    Request:
        `GET` `/favourites[?pl=...]`

    Example response:

        {
            'favourites': [
                {'document_id': 1, 'type': 'r', 'folder_id': null,
                 'created_at': '...', 'lang': 'fr', 'title': '...',
                 'title_prefix': '...'}
            ],
            'folders': [
                {'id': 12, 'name': '...', 'position': 0, 'created_at': '...'}
            ]
        }
    """
    user_id = request.authenticated_userid
    lang = request.validated.get('lang')
    if lang is None:
        lang = DBSession.query(User.lang).filter(User.id == user_id).scalar()

    favourites = (
        DBSession.query(Favourite)
        .filter(Favourite.user_id == user_id)
        .order_by(Favourite.created_at.desc(), Favourite.document_id.desc())
        .all()
    )
    locales = _best_locales([f.document_id for f in favourites], lang)
    return {
        'favourites': [
            _favourite_json(f, locales.get(f.document_id)) for f in favourites
        ],
        'folders': _folders_json(user_id),
    }


def _best_locales(document_ids, lang):
    """Return the best locale of each document: {id: (lang, title, prefix)}."""
    if not document_ids:
        return {}
    # the table of the route locales only: the prefix of their title
    route_locales = RouteLocale.__table__
    rows = (
        DBSession.query(
            DocumentLocale.document_id,
            DocumentLocale.lang,
            DocumentLocale.title,
            route_locales.c.title_prefix,
        )
        .outerjoin(route_locales, route_locales.c.id == DocumentLocale.id)
        .filter(DocumentLocale.document_id.in_(document_ids))
        .all()
    )
    by_document = {}
    for document_id, locale_lang, title, prefix in rows:
        by_document.setdefault(document_id, {})[locale_lang] = (
            locale_lang,
            title,
            prefix,
        )
    return {
        document_id: get_best_locale(available, lang)
        for document_id, available in by_document.items()
    }


def _favourite_json(favourite, locale):
    locale_lang, title, prefix = locale or (None, None, None)
    return {
        'document_id': favourite.document_id,
        'type': favourite.document_type,
        'folder_id': favourite.folder_id,
        'created_at': favourite.created_at.isoformat(),
        'lang': locale_lang,
        'title': title,
        'title_prefix': prefix,
    }


def _ordered_folders(user_id):
    return (
        DBSession.query(FavouriteFolder)
        .filter(FavouriteFolder.user_id == user_id)
        .order_by(FavouriteFolder.position, FavouriteFolder.id)
        .all()
    )


def _folder_json(folder):
    return {
        'id': folder.id,
        'name': folder.name,
        'position': folder.position,
        'created_at': folder.created_at.isoformat(),
    }


def _folders_json(user_id):
    return [_folder_json(f) for f in _ordered_folders(user_id)]


def read_folders(request):
    """List the favourite folders of the authenticated user, in their order.

    Request:
        `GET` `/favourites/folders`

    Example response:

        {'folders': [{'id': 12, 'name': '...', 'position': 0, 'created_at': ...}]}
    """
    return {'folders': _folders_json(request.authenticated_userid)}


def _folder_name(request):
    """Return the stripped name of the body, after checking it is free."""
    # the name of another folder of the user (unique); the folder being
    # renamed may keep its name
    name = request.validated['name'].strip()
    if not name:
        raise HTTPBadRequest('The name of a folder cannot be empty.')
    clash = (
        DBSession.query(FavouriteFolder.id)
        .filter(FavouriteFolder.user_id == request.authenticated_userid)
        .filter(FavouriteFolder.name == name)
        .scalar()
    )
    if clash is not None and clash != request.validated.get('id'):
        raise HTTPBadRequest(f'A folder is already named {name}.')
    return name


@write(
    validators=[body_validator(FolderSchema)],
    permission='authenticated',
    json=True,
)
def create_folder(request):
    """Create a favourite folder, after the others.

    Request:
        `POST` `/favourites/folders`

    Request body:
        {'name': '...'}

    Example response:

        {'id': 12, 'name': '...', 'position': 3, 'created_at': '...'}
    """
    user_id = request.authenticated_userid
    name = _folder_name(request)
    last = (
        DBSession.query(func.max(FavouriteFolder.position))
        .filter(FavouriteFolder.user_id == user_id)
        .scalar()
    )
    folder = FavouriteFolder(
        user_id=user_id, name=name, position=0 if last is None else last + 1
    )
    DBSession.add(folder)
    DBSession.flush()
    DBSession.refresh(folder)
    return _folder_json(folder)


def _own_folder(request):
    folder = _get_folder(request.authenticated_userid, request.validated['id'])
    if folder is None:
        # the folders of the other users are not even said to exist
        raise HTTPNotFound(f'Unknown folder {request.validated["id"]}')
    return folder


@write(
    validators=[validate_id, body_validator(FolderSchema)],
    permission='authenticated',
    json=True,
)
def rename_folder(request):
    """Rename a favourite folder of the authenticated user.

    Request:
        `PUT` `/favourites/folders/{id}`

    Request body:
        {'name': '...'}
    """
    folder = _own_folder(request)
    folder.name = _folder_name(request)
    DBSession.flush()
    return _folder_json(folder)


@write(validators=[validate_id], permission='authenticated', json=True)
def delete_folder(request):
    """Delete a favourite folder; its favourites go back to the main list.

    Request:
        `DELETE` `/favourites/folders/{id}`
    """
    folder = _own_folder(request)
    # done by the foreign key too (ON DELETE SET NULL), but the session
    # may hold the favourites
    DBSession.query(Favourite).filter(Favourite.folder_id == folder.id).update(
        {Favourite.folder_id: None}, synchronize_session='fetch'
    )
    DBSession.delete(folder)
    return {}


@write(
    validators=[body_validator(FolderOrderSchema)],
    permission='authenticated',
    json=True,
)
def order_folders(request):
    """Order the favourite folders of the authenticated user.

    The folders listed come first, in this order, then the others as they were.

    Request:
        `POST` `/favourites/folders/order`

    Request body:
        {'folder_ids': [12, 10, 11]}

    Example response:

        {'folders': [...]}
    """
    user_id = request.authenticated_userid
    folder_ids = request.validated.get('folder_ids') or []
    folders = _ordered_folders(user_id)
    by_id = {f.id: f for f in folders}
    if len(set(folder_ids)) != len(folder_ids):
        raise HTTPBadRequest('A folder is listed twice.')
    unknown = [i for i in folder_ids if i not in by_id]
    if unknown:
        raise HTTPBadRequest(f'Unknown folders: {unknown}')

    listed = [by_id[i] for i in folder_ids]
    others = [f for f in folders if f.id not in set(folder_ids)]
    for position, folder in enumerate(listed + others):
        folder.position = position
    DBSession.flush()
    return {'folders': _folders_json(user_id)}
