"""
Standalone ``objectify()`` implementation.

Converts a validated dict (from pydantic or similar) into a SQLAlchemy
model instance, recursing into relationships for ``locales`` and
``geometry``.
"""

import logging

from sqlalchemy import inspect as sa_inspect

from c2corg_api.models import document_locale_types
from c2corg_api.models.document import DocumentGeometry

log = logging.getLogger(__name__)


def _get_locale_class(sa_model):
    """Return the correct DocumentLocale subclass for *sa_model*.

    Uses the ``polymorphic_identity`` (the document ``type`` char) to look up
    the locale class from the central ``document_locale_types`` mapping.  If
    the model is not a polymorphic document (e.g. ``User``), returns ``None``.
    """
    mapper_args = getattr(sa_model, '__mapper_args__', {})
    poly_id = mapper_args.get('polymorphic_identity')
    if poly_id is not None:
        return document_locale_types.get(poly_id)
    return None


def objectify(sa_model, data):
    """Convert a validated dict *data* into an instance of *sa_model*.

    Handles:
    - scalar column attributes (set directly)
    - ``geometry`` relationship → ``DocumentGeometry``
    - ``locales`` relationship → the model-specific locale class
    - other dict-valued relationships are recursed generically

    Keys in *data* that do not correspond to a mapped property (e.g.
    ``associations``, ``message``) are silently ignored.
    """
    mapper = sa_inspect(sa_model)
    instance = sa_model()

    rel_keys = {r.key: r for r in mapper.relationships}
    col_keys = {c.key for c in mapper.column_attrs}
    locale_class = _get_locale_class(sa_model)

    # Track which keys were explicitly provided in *data* so that
    # ``copy_attributes`` can later distinguish "explicitly set to None"
    # from "not provided at all (SA default None)".
    provided_keys = set()

    for key, value in data.items():
        if value is None:
            # Skip None so we don't overwrite
            # defaults on the model (nullable columns stay None anyway).
            if key in col_keys:
                setattr(instance, key, None)
                provided_keys.add(key)
            continue

        if key in rel_keys:
            rel = rel_keys[key]
            if rel.uselist:
                # One-to-many (e.g. ``locales``)
                if isinstance(value, list):
                    target_class = _target_class_for_rel(key, rel, locale_class)
                    setattr(
                        instance,
                        key,
                        [
                            objectify(target_class, item)
                            if isinstance(item, dict)
                            else item
                            for item in value
                        ],
                    )
                    provided_keys.add(key)
            else:
                # Many-to-one / one-to-one (e.g. ``geometry``)
                if isinstance(value, dict):
                    target_class = _target_class_for_rel(key, rel, locale_class)
                    setattr(instance, key, objectify(target_class, value))
                else:
                    setattr(instance, key, value)
                provided_keys.add(key)
        elif key in col_keys:
            setattr(instance, key, value)
            provided_keys.add(key)
        else:
            # Silently ignore unknown keys (associations, message, …)
            log.debug(
                'objectify: %s not found on %s — ignored.', key, sa_model.__name__
            )

    # Store the set of explicitly provided keys so that downstream code
    # (e.g. ``copy_attributes``) can distinguish "explicitly set to None"
    # from "not provided at all (SA default is None)".
    instance._objectify_fields = provided_keys

    return instance


def clear_objectify_fields(instance):
    """Clear ``_objectify_fields`` on *instance* and its sub-objects.

    Should be called after the objectified instance has been merged into
    the SA session (via ``update()`` or ``add()`` + ``flush()``) so that
    subsequent operations like ``to_archive()`` are not affected by the
    field filter.
    """
    if hasattr(instance, '_objectify_fields'):
        instance._objectify_fields = None
    for locale in getattr(instance, 'locales', None) or []:
        if hasattr(locale, '_objectify_fields'):
            locale._objectify_fields = None
    geom = getattr(instance, 'geometry', None)
    if geom is not None and hasattr(geom, '_objectify_fields'):
        geom._objectify_fields = None


def _target_class_for_rel(key, rel, locale_class):
    """Return the SA model class to instantiate for relationship *key*.

    Special cases:
    - ``locales`` → model-specific locale class (e.g. ``RouteLocale``)
    - ``geometry`` → ``DocumentGeometry``
    - everything else → the mapper's target class
    """
    if key == 'locales' and locale_class is not None:
        return locale_class
    if key == 'geometry':
        return DocumentGeometry
    return rel.mapper.class_
