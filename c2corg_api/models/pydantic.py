"""
Pydantic schema generation from SQLAlchemy models.

This module is the pydantic counterpart of ColanderAlchemy: it introspects
SQLAlchemy mapped classes and produces pydantic ``BaseModel`` subclasses
whose fields mirror the mapped columns.

It also provides reusable base schemas for locales, geometry and
associations that parallel the colander equivalents defined in
``models.document`` and ``models.schema_utils``.

Usage::

    from c2corg_api.models.pydantic import (
        schema_from_sa_model, get_update_schema,
        DocumentGeometrySchema, AssociationsSchema,
    )
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Literal, Optional, Sequence, Type

import datetime

from pydantic import BaseModel, create_model, model_validator
from sqlalchemy import (
    inspect as sa_inspect, Integer, String, Boolean, Enum,
    Date, DateTime, Float, SmallInteger,
)
from sqlalchemy.dialects.postgresql import ARRAY

from c2corg_api.models.utils import ArrayOfEnum
from c2corg_api.models.common.attributes import default_langs

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Reusable Literal type for languages
# ---------------------------------------------------------------------------

LangType = Literal[tuple(default_langs)]  # type: ignore[valid-type]

# ---------------------------------------------------------------------------
# Helpers: SQLAlchemy column type → Python / pydantic type
# ---------------------------------------------------------------------------


def _literal_from_sa_enum(sa_enum: Enum):
    """Build a ``Literal[...]`` type from a SQLAlchemy ``Enum`` column type."""
    return Literal[tuple(sa_enum.enums)]  # type: ignore[valid-type]


_SA_TYPE_MAP = {
    Integer: int,
    SmallInteger: int,
    Float: float,
    String: str,
    Boolean: bool,
    Date: datetime.date,
    DateTime: datetime.datetime,
}


def _python_type_for_column(col) -> type:
    """Return the Python type that corresponds to a SA column type."""
    col_type = col.type

    # ArrayOfEnum / ARRAY(Enum)
    if isinstance(col_type, (ArrayOfEnum, ARRAY)):
        item = getattr(col_type, 'item_type', None)
        if (
            item is None
            and hasattr(col_type, 'impl')
            and hasattr(
                col_type.impl, 'item_type'
            )
        ):
            item = col_type.impl.item_type
        if item is not None and isinstance(item, Enum):
            return List[
                _literal_from_sa_enum(item)
            ]  # type: ignore[valid-type]
        return List[str]  # type: ignore[valid-type]

    # Plain Enum
    if isinstance(item_type := col_type, Enum):
        return _literal_from_sa_enum(item_type)

    # Scalar types
    for sa_cls, py_type in _SA_TYPE_MAP.items():
        if isinstance(col_type, sa_cls):
            return py_type

    # Fallback
    return Any


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def schema_from_sa_model(
    sa_model: type,
    *,
    name: str | None = None,
    includes: Sequence[str] | None = None,
    overrides: Dict[str, Dict[str, Any]] | None = None,
    extra_fields: Dict[str, Any] | None = None,
    base: Type[BaseModel] = BaseModel,
) -> Type[BaseModel]:
    """Create a pydantic model whose fields are derived from *sa_model*.

    Parameters
    ----------
    sa_model:
        A SQLAlchemy mapped class (e.g. ``UserProfile``).
    name:
        Name of the generated pydantic class.  Defaults to
        ``<sa_model.__name__>PydanticSchema``.
    includes:
        Whitelist of column / relationship names to include.  If ``None``
        every mapped column is included.
    overrides:
        Per-field overrides.  Each key is a field name and its value a dict
        that may contain ``type`` (override the inferred Python type) and/or
        ``default`` (override the default value).
    extra_fields:
        Additional fields that do not correspond to a column on the model
        (e.g. ``associations``).  Each value should be a ``(type, default)``
        tuple as expected by :func:`pydantic.create_model`.
    base:
        Base class for the generated model.
    """
    overrides = overrides or {}
    extra_fields = extra_fields or {}
    model_name = name or f'{sa_model.__name__}PydanticSchema'

    mapper = sa_inspect(sa_model)
    field_definitions: Dict[str, Any] = {}

    # ---- columns -----------------------------------------------------------
    for attr in mapper.column_attrs:
        col_name = attr.key
        if includes is not None and col_name not in includes:
            continue
        # skip internal polymorphic discriminators
        if col_name == 'type':
            continue

        col = attr.columns[0]
        ov = overrides.get(col_name, {})
        py_type = ov.get('type', _python_type_for_column(col))

        nullable = col.nullable if col.nullable is not None else True
        has_default = 'default' in ov
        if has_default:
            default = ov['default']
        elif col.default is not None and col.default.is_scalar:
            # Use the column's Python-side default (e.g. 'no' for
            # glacier_gear) so that objectify receives the right value
            # when the user omits the field.
            default = col.default.arg
        elif nullable or not col.nullable:
            default = None
        else:
            default = ...  # required

        # Wrap in Optional when a default of None is used
        if default is None:
            py_type = Optional[py_type]

        field_definitions[col_name] = (py_type, default)

    # ---- relationships (locales, geometry) ---------------------------------
    for rel in mapper.relationships:
        rel_name = rel.key
        if includes is not None and rel_name not in includes:
            continue
        ov = overrides.get(rel_name, {})
        if 'type' not in ov:
            # Skip relationships without an explicit override type —
            # callers must provide the pydantic sub-schema.
            continue
        py_type = ov['type']
        default = ov.get('default', None)
        if default is None:
            py_type = Optional[py_type]
        field_definitions[rel_name] = (py_type, default)

    # ---- extra fields (not on the SA model) --------------------------------
    field_definitions.update(extra_fields)

    return create_model(
        model_name, __base__=base, **field_definitions)


# ---------------------------------------------------------------------------
# Reusable base schemas (parallel to colander equivalents)
# ---------------------------------------------------------------------------


class DocumentLocaleSchema(BaseModel):
    """Pydantic equivalent of ``schema_document_locale`` (with title).

    Mirrors ``schema_locale_attributes``:
    ``['version', 'lang', 'title', 'description', 'summary']``.
    """
    lang: LangType  # type: ignore[valid-type]
    version: Optional[int] = None
    title: Optional[str] = None
    description: Optional[str] = None
    summary: Optional[str] = None

    model_config = {"extra": "ignore"}


class DocumentGeometrySchema(BaseModel):
    """Pydantic equivalent of the colander geometry schema."""
    version: Optional[int] = None
    geom: Optional[str] = None
    geom_detail: Optional[str] = None

    model_config = {"extra": "ignore"}


class AssociationRefSchema(BaseModel):
    document_id: int


class AssociationsSchema(BaseModel):
    """Pydantic equivalent of ``SchemaAssociations`` in
    ``models.schema_utils``."""
    users: Optional[List[AssociationRefSchema]] = None
    routes: Optional[List[AssociationRefSchema]] = None
    xreports: Optional[List[AssociationRefSchema]] = None
    waypoints: Optional[List[AssociationRefSchema]] = None
    waypoint_children: Optional[List[AssociationRefSchema]] = None
    books: Optional[List[AssociationRefSchema]] = None
    images: Optional[List[AssociationRefSchema]] = None
    articles: Optional[List[AssociationRefSchema]] = None
    outings: Optional[List[AssociationRefSchema]] = None
    coverages: Optional[List[AssociationRefSchema]] = None

    model_config = {"extra": "ignore"}


class _DuplicateLocalesMixin:
    """Mixin that adds a model validator rejecting duplicate locales."""

    @model_validator(mode='after')
    def check_no_duplicate_locales(self):
        locales = getattr(self, 'locales', None)
        if locales:
            seen: set = set()
            for loc in locales:
                lang = loc.lang
                if lang in seen:
                    raise ValueError(
                        f'lang "{lang}" is given twice')
                seen.add(lang)
        return self


def get_update_schema(
    document_schema: Type[BaseModel],
    *,
    name: str | None = None,
) -> Type[BaseModel]:
    """Wrap a document pydantic schema into an update envelope
    with ``message`` and ``document`` keys.

    Mirrors ``schema_utils.get_update_schema`` for colander.
    """
    schema_name = name or f'Update{document_schema.__name__}'
    return create_model(
        schema_name,
        message=(str, ''),
        document=(document_schema, ...),
    )


def get_create_schema(
    document_schema: Type[BaseModel],
    *,
    name: str | None = None,
) -> Type[BaseModel]:
    """Return *document_schema* unchanged (associations are already
    part of the document schema).

    Mirrors ``schema_utils.get_create_schema`` for colander, which
    simply adds an ``associations`` field — our pydantic document
    schemas already include it.
    """
    # Nothing to wrap; the create body IS the document.
    return document_schema
