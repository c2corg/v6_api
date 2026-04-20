"""
Shared validation helpers and parameter types for FastAPI routers.

No Pyramid / Cornice dependency.

Provides:
- ``Annotated`` path-parameter types and query-parameter dataclass bundles
- ``ErrorCollector`` for accumulating validation errors
- Pure validation functions (field checks, association checks, permissions)
"""

import functools
from dataclasses import dataclass
from typing import Annotated, Optional

from fastapi import Depends, HTTPException, Path, Query
from sqlalchemy import and_, exists
from sqlalchemy.orm import Session

from c2corg_api.database import get_db
from c2corg_api.models import article, image
from c2corg_api.models.area import AREA_TYPE
from c2corg_api.models.article import ARTICLE_TYPE
from c2corg_api.models.association import (
    Association,
    association_keys,
    updatable_associations,
)
from c2corg_api.models.book import BOOK_TYPE
from c2corg_api.models.common.associations import valid_associations
from c2corg_api.models.common.attributes import DefaultLangs
from c2corg_api.models.document import Document
from c2corg_api.models.document_history import has_been_created_by
from c2corg_api.models.image import IMAGE_TYPE
from c2corg_api.models.outing import OUTING_TYPE
from c2corg_api.models.route import ROUTE_TYPE
from c2corg_api.models.user import User
from c2corg_api.models.user_profile import USERPROFILE_TYPE
from c2corg_api.models.waypoint import WAYPOINT_TYPE, Waypoint
from c2corg_api.models.xreport import XREPORT_TYPE
from c2corg_api.routers.helpers._db_compat import resolve_db as _resolve_db
from c2corg_api.routers.helpers.document_collection import LIMIT_DEFAULT, LIMIT_MAX


# ── Path parameters ──────────────────────────────────────────────

DocumentId = Annotated[int, Path(ge=0, description='Document primary key')]
VersionId = Annotated[int, Path(ge=0, description='Version primary key')]
Language = Annotated[DefaultLangs, Path(description='Language code')]


# ── Query-parameter bundles ──────────────────────────────────────


@dataclass
class CollectionParams:
    """Pagination + preferred-language params for collection GET."""

    offset: int = Query(0, ge=0)
    limit: int = Query(LIMIT_DEFAULT, ge=0, le=LIMIT_MAX)
    pl: Optional[DefaultLangs] = Query(None, description='Preferred language')
    db: Session = Depends(get_db)


@dataclass
class SingleDocParams:
    """Query params for single-document GET."""

    l: Optional[DefaultLangs] = Query(  # noqa: E741
        None, description='Locale language'
    )
    cook: Optional[DefaultLangs] = Query(None, description='Cooking language')
    e: Optional[str] = Query(None)
    db: Session = Depends(get_db)

    @property
    def lang(self) -> Optional[DefaultLangs]:
        return self.l

    @property
    def editing_view(self) -> bool:
        return self.e is not None and self.e != '0'


# ── Error collector ──────────────────────────────────────────────


class ErrorCollector:
    """Mimics ``request.errors`` from Cornice so that existing validation
    helpers (``check_required_fields``, ``validate_associations_in``, …)
    can be reused unchanged.
    """

    def __init__(self):
        self.errors: list[dict] = []

    def add(self, location: str, name: str, description: str):
        self.errors.append(
            {'location': location, 'name': name, 'description': description}
        )

    def extend(self, other):
        """Append errors from another error container.

        *other* can be an ``ErrorCollector`` or any iterable of dicts.
        """
        if hasattr(other, 'errors'):
            self.errors.extend(other.errors)
        else:
            for err in other:
                self.errors.append(err)

    def __bool__(self):
        return bool(self.errors)


# ── Tiny utility (also used by document_associations) ────────────


def get_first_column(rows):
    return [r[0] for r in rows]


# ── Field-level validation ───────────────────────────────────────


def is_missing(val):
    return val is None or val == '' or val == []


def check_required_fields(document, fields, request, updating):
    """Checks that the given fields are set on the document.

    *request* must expose ``request.errors.add(location, name, description)``.
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
            field_parts = field.split('.')
            attr = document.get(field_parts[0])
            if attr is not None:
                if isinstance(attr, list):
                    # e.g. 'locales.title' – check each entry
                    for i, item in enumerate(attr):
                        if is_missing(item.get(field_parts[1])):
                            request.errors.add(
                                'body',
                                '{}.{}.{}'.format(field_parts[0], i, field_parts[1]),
                                'Required',
                            )
                else:
                    if is_missing(attr.get(field_parts[1])):
                        request.errors.add('body', field, 'Required')


def check_duplicate_locales(document, request):
    """Check that there is only one entry for each lang.

    *request* must expose ``request.errors.add(location, name, description)``.
    """
    locales = document.get('locales')
    if locales:
        langs = set()
        for locale in locales:
            lang = locale.get('lang')
            if lang in langs:
                request.errors.add(
                    'body', 'locales', 'lang "%s" is given twice' % (lang)
                )
                return
            langs.add(lang)


# ── Convenience wrappers ─────────────────────────────────────────


def validate_required(
    document_dict: dict, required_fields: list[str], updating: bool
) -> list[dict]:
    """Run required-field + duplicate-locale checks.

    Returns the (possibly empty) list of error dicts.
    """
    ec = ErrorCollector()
    _req = type('R', (), {'errors': ec})()
    check_required_fields(document_dict, required_fields, _req, updating)
    check_duplicate_locales(document_dict, _req)
    return ec.errors


def validate_associations(associations_in, document_type, *, db):
    """Validate incoming associations dict.

    Returns ``(validated_dict, errors_list)``.
    """
    ec = ErrorCollector()
    validated = validate_associations_in(associations_in, document_type, ec, db=db)
    return validated, ec.errors


def raise_on_errors(errors: list[dict]):
    """Raise an ``HTTPException`` whose body matches Cornice's error format
    if *errors* is non-empty.
    """
    if errors:
        raise HTTPException(
            status_code=400, detail={'status': 'error', 'errors': errors}
        )


# ── Association validation ───────────────────────────────────────


def validate_associations_in(
    associations_in, document_type, errors, db: Session | None = None
):
    """Validate the provided associations:

        - Check that the linked documents exist.
        - Check that the linked documents have the right document type (e.g. a
          document listed as route association must really be a route).
        - Check that only valid association combinations are given.

    *errors* must expose ``.add(location, name, description)`` **and**
    support ``if errors:`` truthiness and ``.extend(other)``.

    Returns the validated associations.
    """

    class _Errors:
        """Lightweight error list compatible with the extend/bool protocol."""

        def __init__(self):
            self._items: list[dict] = []

        def add(self, location, name, description):
            self._items.append(
                {'location': location, 'name': name, 'description': description}
            )

        def __bool__(self):
            return bool(self._items)

        def __iter__(self):
            return iter(self._items)

    new_errors = _Errors()
    associations = {}
    db = _resolve_db(db)

    _add_associations(
        associations,
        associations_in,
        document_type,
        'users',
        USERPROFILE_TYPE,
        new_errors,
    )
    _add_associations(
        associations, associations_in, document_type, 'routes', ROUTE_TYPE, new_errors
    )
    _add_associations(
        associations,
        associations_in,
        document_type,
        'waypoints',
        WAYPOINT_TYPE,
        new_errors,
    )
    _add_associations(
        associations, associations_in, document_type, 'images', IMAGE_TYPE, new_errors
    )
    _add_associations(
        associations,
        associations_in,
        document_type,
        'articles',
        ARTICLE_TYPE,
        new_errors,
    )
    _add_associations(
        associations,
        associations_in,
        document_type,
        'waypoint_children',
        WAYPOINT_TYPE,
        new_errors,
    )
    _add_associations(
        associations, associations_in, document_type, 'areas', AREA_TYPE, new_errors
    )
    _add_associations(
        associations, associations_in, document_type, 'outings', OUTING_TYPE, new_errors
    )
    _add_associations(
        associations, associations_in, document_type, 'books', BOOK_TYPE, new_errors
    )
    _add_associations(
        associations,
        associations_in,
        document_type,
        'xreports',
        XREPORT_TYPE,
        new_errors,
    )

    if new_errors:
        errors.extend(new_errors)
        return None

    _check_for_valid_documents_ids(associations, new_errors, db=db)

    if new_errors:
        errors.extend(new_errors)
        return None
    else:
        return associations


# ── Association permission helpers ───────────────────────────────


def validate_association_permission(
    user_id,
    is_moderator,
    parent_document_id,
    parent_document_type,
    child_document_id,
    child_document_type,
    errors=None,
    skip_outing_check=False,
):
    """Check whether *user_id* may modify an association.

    When *errors* (an ``ErrorCollector`` or list-like with ``.add()``) is
    provided, validation messages are appended there.  When *errors* is
    ``None``, an ``HTTPException(400)`` is raised on the first failure.
    """
    if is_moderator:
        return

    if not skip_outing_check and OUTING_TYPE in (
        parent_document_type,
        child_document_type,
    ):
        _validate_outing_association(
            user_id,
            is_moderator,
            parent_document_id,
            parent_document_type,
            child_document_id,
            child_document_type,
            errors,
        )

    if IMAGE_TYPE in (parent_document_type, child_document_type):
        _validate_image_association(
            user_id,
            parent_document_id,
            parent_document_type,
            child_document_id,
            child_document_type,
            errors,
        )

    if ARTICLE_TYPE in (parent_document_type, child_document_type):
        _validate_article_association(
            user_id,
            parent_document_id,
            parent_document_type,
            child_document_id,
            child_document_type,
            errors,
        )

    if XREPORT_TYPE in (parent_document_type, child_document_type):
        _validate_xreport_association(
            user_id,
            parent_document_id,
            parent_document_type,
            child_document_id,
            child_document_type,
            errors,
        )


def check_permission_for_association(
    user_id, is_moderator, association, skip_outing_check=False
):
    """Raises ``HTTPException(400)`` when the user may not create this association."""
    validate_association_permission(
        user_id,
        is_moderator,
        association.parent_document_id,
        association.parent_document_type,
        association.child_document_id,
        association.child_document_type,
        errors=None,
        skip_outing_check=skip_outing_check,
    )


def association_permission_checker(user_id, is_moderator, skip_outing_check=False):
    """Return a callable ``check(association)`` for ``create_associations``."""

    def check(association):
        check_permission_for_association(
            user_id, is_moderator, association, skip_outing_check
        )

    return check


def association_permission_removal_checker(user_id, is_moderator):
    """Return a callable ``check(association)`` for ``synchronize_associations``."""
    return functools.partial(
        check_permission_for_association_removal, user_id, is_moderator
    )


def check_permission_for_association_removal(user_id, is_moderator, association):
    """Check whether *user_id* may remove an association.

    Raises ``HTTPException(400)`` when not permitted.
    """
    if is_moderator:
        return

    valid_parent = _check_permission_association_doc(
        user_id, association.parent_document_type, association.parent_document_id
    )
    valid_child = _check_permission_association_doc(
        user_id, association.child_document_type, association.child_document_id
    )

    if not valid_parent and not valid_child:
        raise HTTPException(
            status_code=400,
            detail='no rights to modify associations between document '
            '{} ({}) and {} ({})'.format(
                association.parent_document_type,
                association.parent_document_id,
                association.child_document_type,
                association.child_document_id,
            ),
        )


def has_permission_for_outing(
    user_id, is_moderator, outing_id, db: Session | None = None
):
    """Check if *user_id* has permission to change an outing.

    Only users currently assigned to the outing (or moderators) may modify it.
    """
    db = _resolve_db(db)
    if is_moderator:
        return True

    return db.query(
        exists().where(
            and_(
                Association.parent_document_id == user_id,
                Association.child_document_id == outing_id,
            )
        )
    ).scalar()


# ── xreport helpers ──────────────────────────────────────────────


def get_associated_user_ids(xreport_id, db: Session | None = None):
    db = _resolve_db(db)
    associated_user_ids = get_first_column(
        db.query(User.id)
        .join(Association, Association.parent_document_id == User.id)
        .filter(Association.child_document_id == xreport_id)
        .group_by(User.id)
        .all()
    )
    return associated_user_ids


def is_associated_user(xreport_id, user_id, db: Session | None = None):
    """Required to check if an associated user is able to edit Xreport."""
    associated_user_ids = get_associated_user_ids(xreport_id, db=db)
    if user_id in associated_user_ids:
        return True


# ── Private helpers ──────────────────────────────────────────────


def _validate_outing_association(
    user_id,
    is_moderator,
    parent_document_id,
    parent_document_type,
    child_document_id,
    child_document_type,
    errors,
):
    if parent_document_type != OUTING_TYPE and child_document_type != OUTING_TYPE:
        return

    if parent_document_type == OUTING_TYPE:
        outing_id = parent_document_id
    else:
        outing_id = child_document_id

    if not has_permission_for_outing(user_id, is_moderator, outing_id):
        msg = 'no rights to modify associations with outing {}'.format(outing_id)
        if errors is not None:
            errors.add('body', 'associations.outings', msg)
        else:
            raise HTTPException(status_code=400, detail=msg)


def _validate_article_association(
    user_id,
    parent_document_id,
    parent_document_type,
    child_document_id,
    child_document_type,
    errors,
):
    _validate_personal_association(
        user_id,
        parent_document_id,
        parent_document_type,
        child_document_id,
        child_document_type,
        errors,
        ARTICLE_TYPE,
        article.is_personal,
        'article',
    )


def _validate_image_association(
    user_id,
    parent_document_id,
    parent_document_type,
    child_document_id,
    child_document_type,
    errors,
):
    _validate_personal_association(
        user_id,
        parent_document_id,
        parent_document_type,
        child_document_id,
        child_document_type,
        errors,
        IMAGE_TYPE,
        image.is_personal,
        'image',
    )


def _validate_xreport_association(
    user_id,
    parent_document_id,
    parent_document_type,
    child_document_id,
    child_document_type,
    errors,
):
    _validate_personal_association(
        user_id,
        parent_document_id,
        parent_document_type,
        child_document_id,
        child_document_type,
        errors,
        XREPORT_TYPE,
        lambda _: True,
        'xreport',
    )


def _validate_personal_association(
    user_id,
    parent_document_id,
    parent_document_type,
    child_document_id,
    child_document_type,
    errors,
    doc_type,
    is_personal,
    label,
):
    document_ids = set()
    if parent_document_type == doc_type:
        document_ids.add(parent_document_id)
    if child_document_type == doc_type:
        document_ids.add(child_document_id)

    for document_id in document_ids:
        if (
            is_personal(document_id)
            and not has_been_created_by(document_id, user_id)
            and not is_associated_user(document_id, user_id)
        ):
            msg = 'no rights to modify associations with {} {}'.format(
                label, document_id
            )
            if errors is not None:
                errors.add('body', 'associations.{}s'.format(label), msg)
            else:
                raise HTTPException(status_code=400, detail=msg)


def _check_permission_association_doc(user_id, doc_type, document_id, db=None):
    if doc_type == OUTING_TYPE:
        if has_permission_for_outing(user_id, False, document_id):
            return True
    elif doc_type == IMAGE_TYPE:
        if image.is_personal(document_id) and has_been_created_by(document_id, user_id):
            return True
    elif doc_type == ARTICLE_TYPE:
        if article.is_personal(document_id) and has_been_created_by(
            document_id, user_id
        ):
            return True
    elif doc_type == XREPORT_TYPE:
        if has_been_created_by(document_id, user_id) or is_associated_user(
            document_id, user_id, db=db
        ):
            return True

    return False


def _check_for_valid_documents_ids(associations, errors, db: Session | None = None):
    """Check that the given documents do exist and that they are of the
    correct type.
    """
    db = _resolve_db(db)
    linked_documents_id = _get_linked_document_ids(associations)

    if linked_documents_id:
        query_documents_with_type = (
            db.query(Document.document_id, Document.type)
            .filter(Document.document_id.in_(linked_documents_id))
            .filter(Document.redirects_to.is_(None))
        )
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
                    'body',
                    'associations.' + document_key,
                    'document "{0:n}" does not exist or is redirected'.format(
                        document_id
                    ),
                )
                continue
            if doc_type != type_for_document_id[str(document_id)]:
                errors.add(
                    'body',
                    'associations.' + document_key,
                    'document "{0:n}" is not of type "{1}"'.format(
                        document_id, doc_type
                    ),
                )


def _get_linked_document_ids(associations):
    return set().union(
        *[[doc['document_id'] for doc in docs] for docs in associations.values()]
    )


def _is_any_climbing_indoor_waypoint(associations_in, db: Session | None = None):
    db = _resolve_db(db)
    waypoints_id = [doc['document_id'] for doc in associations_in['waypoints']]

    if waypoints_id:
        query_waypoints_with_type = db.query(Waypoint.waypoint_type).filter(
            Waypoint.document_id.in_(waypoints_id)
        )
        for waypoint in query_waypoints_with_type.all():
            if waypoint.waypoint_type == 'climbing_indoor':
                return True
    return False


def _add_associations(
    associations,
    associations_in,
    main_document_type,
    document_key,
    other_document_type,
    errors,
):
    valid_types = updatable_associations.get(main_document_type, set())

    if document_key not in valid_types:
        return

    associations_for_type = associations_in.get(document_key, None)
    if associations_for_type is not None:
        is_parent = _is_parent_of_association(main_document_type, other_document_type)

        if is_parent is None:
            errors.add(
                'body', 'associations.' + document_key, 'invalid association type'
            )
            return

        if document_key == 'waypoints' and main_document_type == ROUTE_TYPE:
            if _is_any_climbing_indoor_waypoint(associations_in):
                errors.add(
                    'body',
                    'associations.climbing_indoor_waypoint',
                    'climbing_indoor waypoint cannot be linked to a route',
                )
                return
        elif document_key == 'waypoints' and main_document_type != BOOK_TYPE:
            is_parent = True
        elif document_key == 'waypoint_children':
            is_parent = False

        associations[document_key] = [
            {'document_id': doc['document_id'], 'is_parent': is_parent}
            for doc in associations_in[document_key]
        ]


def _is_parent_of_association(main_document_type, other_document_type):
    if (main_document_type, other_document_type) in valid_associations:
        return False
    elif (other_document_type, main_document_type) in valid_associations:
        return True
    else:
        return None
