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

    for key, value in data.items():
        if value is None:
            # Skip None so we don't overwrite
            # defaults on the model (nullable columns stay None anyway).
            if key in col_keys:
                setattr(instance, key, None)
            continue

        if key in rel_keys:
            rel = rel_keys[key]
            if rel.uselist:
                # One-to-many (e.g. ``locales``)
                if isinstance(value, list):
                    target_class = _target_class_for_rel(
                        key, rel, locale_class)
                    setattr(instance, key, [
                        objectify(target_class, item)
                        if isinstance(item, dict) else item
                        for item in value
                    ])
            else:
                # Many-to-one / one-to-one (e.g. ``geometry``)
                if isinstance(value, dict):
                    target_class = _target_class_for_rel(
                        key, rel, locale_class)
                    setattr(instance, key, objectify(target_class, value))
                else:
                    setattr(instance, key, value)
        elif key in col_keys:
            setattr(instance, key, value)
        else:
            # Silently ignore unknown keys (associations, message, …)
            log.debug(
                "objectify: %s not found on %s — ignored.",
                key, sa_model.__name__,
            )

    return instance


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
