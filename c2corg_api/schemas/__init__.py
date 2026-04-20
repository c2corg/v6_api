"""
Pydantic schemas for API validation and serialization.

Shared base schemas live here.

Convention
----------
- ``*Create``  — POST request body validation
- ``*Update``  — PUT  request body validation (wraps document + message)
- ``*Read``    — GET  response serialization  (future use with FastAPI)

All schemas set ``model_config = {"extra": "ignore"}`` so that unknown
fields from the request body are silently dropped, matching the existing
API behaviour.
"""

from __future__ import annotations

import datetime  # noqa: F401 — re-exported for use in document Read schemas
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, model_validator

from c2corg_api.models.common.attributes import DefaultLangs
from c2corg_api.schemas.geometry import (  # noqa: F401 — re-exported
    DIM_2D,
    DIM_2D_3D_4D,
    GeometryField,
    validate_geojson,
)

# ---------------------------------------------------------------------------
# Module-level GeometryField type aliases.
# GeometryField.*() returns a dynamic ``type``, not a static generic alias.
# Pylance cannot resolve these in type expressions; suppress with
# ``type: ignore[valid-type]`` on each field or use ``Any`` for type
# checkers while keeping full runtime behaviour via GeometryField.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Locale schemas
# ---------------------------------------------------------------------------


class DocumentLocaleSchema(BaseModel):
    """Base locale schema for create/update requests.

    Mirrors ``schema_locale_attributes``:
    ``['version', 'lang', 'title', 'description', 'summary']``
    """

    lang: DefaultLangs
    version: Optional[int] = None
    title: Optional[str] = None
    description: Optional[str] = None
    summary: Optional[str] = None

    model_config = ConfigDict(extra='ignore')


# ---------------------------------------------------------------------------
# Geometry schemas
# ---------------------------------------------------------------------------
# The DB stores ``geom`` as POINT (srid=3857, 2D) and ``geom_detail`` as
# GEOMETRY (srid=3857, unconstrained type/dimension) for every document
# that has a ``documents_geometries`` row.
#
# However, not every document type uses both columns and different types
# accept different geometry kinds for ``geom_detail``.
#
# We define *typed* geometry schemas so that each document type can declare
# exactly which fields are accepted and which GeoJSON geometry types are
# valid.  The ``allowed_geometry_types`` list on ``make_pydantic_validator``
# still performs the actual GeoJSON→WKB conversion and type-checking at
# runtime; these schemas enforce the *structural* contract (which fields
# are required / optional / absent).
#
# Layout:
#   geom        — always a POINT when present
#   geom_detail — varies: LINESTRING, POLYGON, … depending on doc type
#
# ┌──────────────┬───────────────┬─────────────────────────────────────────┐
# │ Doc type     │ geom (POINT)  │ geom_detail                             │
# ├──────────────┼───────────────┼─────────────────────────────────────────┤
# │ Waypoint     │ required      │ POINT (optional, same as geom)           │
# │ Route        │ optional*     │ LINESTRING / MULTILINESTRING            │
# │ Outing       │ optional*     │ LINESTRING / MULTILINESTRING            │
# │ Image        │ optional      │ —                                       │
# │ XReport      │ optional      │ —                                       │
# │ Area         │ —             │ POLYGON / MULTIPOLYGON                  │
# │ Topo Map     │ —             │ POLYGON / MULTIPOLYGON                  │
# │ Coverage     │ —             │ POLYGON (strict)                        │
# │ User Profile │ optional      │ —                                       │
# │ Book         │ (no geometry) │ (no geometry)                           │
# │ Article      │ (no geometry) │ (no geometry)                           │
# └──────────────┴───────────────┴─────────────────────────────────────────┘
#   * Route/Outing ``geom`` is auto-derived from associated waypoints/routes
#     but can be supplied explicitly.


# Note: GeometryField.*() produces a dynamic class at runtime, not a static
# generic alias. Pylance cannot resolve it in type expressions; each field
# carries ``type: ignore[valid-type]`` to suppress the false positive.
# The ``noqa: E501`` suppresses line-length checks on these lines.


class PointGeometrySchema(BaseModel):
    """Geometry with only a ``geom`` (POINT, strictly 2D) field.

    Suitable for images, xreports, user profiles.
    The DB column is declared ``POINT, dimension=2`` so only 2D is accepted.
    Validates type/dims and converts GeoJSON str ↔ WKBElement automatically.
    """

    version: Optional[int] = None
    geom: Optional[GeometryField.point_2d()] = None  # type: ignore[valid-type]

    model_config = ConfigDict(extra='ignore')


class WaypointGeometrySchema(BaseModel):
    """Geometry with ``geom`` (POINT 2D) and optional ``geom_detail`` (POINT 2D).

    Waypoints store a POINT in both columns (general vs. precise location).
    The DB ``geom`` column is declared ``POINT, dimension=2``; both fields
    are strictly 2D.
    """

    version: Optional[int] = None
    geom: Optional[GeometryField.point_2d()] = None  # type: ignore[valid-type]
    geom_detail: Optional[GeometryField.point_2d()] = None  # type: ignore[valid-type]

    model_config = ConfigDict(extra='ignore')


class LineGeometrySchema(BaseModel):
    """Geometry for routes and outings.

    - ``geom``        — POINT strictly 2D (DB column: ``POINT, dimension=2``).
    - ``geom_detail`` — LINESTRING / MULTILINESTRING, 2D–4D.
      GPS tracks may carry elevation (Z) and timestamps (M); all four
      dimensions are accepted on the way in and stored faithfully.
    """

    version: Optional[int] = None
    geom: Optional[GeometryField.point_2d()] = None  # type: ignore[valid-type]  # noqa: E501
    geom_detail: Optional[GeometryField.line()] = None  # type: ignore[valid-type]  # noqa: E501

    model_config = ConfigDict(extra='ignore')


class PolygonGeometrySchema(BaseModel):
    """Geometry with ``geom_detail`` (POLYGON or MULTIPOLYGON, strictly 2D).

    Suitable for areas.  Area boundaries are always 2D.
    """

    version: Optional[int] = None
    geom_detail: Optional[GeometryField.polygon()] = None  # type: ignore[valid-type]  # noqa: E501

    model_config = ConfigDict(extra='ignore')


class StrictPolygonGeometrySchema(BaseModel):
    """Geometry with ``geom_detail`` (POLYGON only, strictly 2D).

    Suitable for topo maps and coverages.
    """

    version: Optional[int] = None
    geom_detail: Optional[GeometryField.strict_polygon()] = None  # type: ignore[valid-type]  # noqa: E501

    model_config = ConfigDict(extra='ignore')


# ---------------------------------------------------------------------------
# Association schemas
# ---------------------------------------------------------------------------


class AssociationRefSchema(BaseModel):
    document_id: int


class AssociationsSchema(BaseModel):
    """Nested associations block for create/update requests."""

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

    model_config = ConfigDict(extra='ignore')


# ---------------------------------------------------------------------------
# Duplicate-locale mixin
# ---------------------------------------------------------------------------


class DuplicateLocalesMixin:
    """Mixin that rejects duplicate ``lang`` values in ``locales``."""

    @model_validator(mode='after')
    def check_no_duplicate_locales(self):
        locales = getattr(self, 'locales', None)
        if locales:
            seen: set = set()
            for loc in locales:
                lang = loc.lang
                if lang in seen:
                    raise ValueError(f'lang "{lang}" is given twice')
                seen.add(lang)
        return self


# =========================================================================
# READ (response) schemas
# =========================================================================
# These schemas are designed for serializing SA instances into JSON
# responses.  They set ``from_attributes = True`` so that Pydantic can
# read directly from SA model attributes (for future FastAPI integration).
#
# Read schemas mirror what ``to_json_dict`` currently returns:
#   - all SA columns from the FieldSpec
#   - "special attributes" bolted on by ``to_json_dict``
#     (available_langs, associations, maps, areas, author, protected,
#      type, name, forum_username, creator, img_count)
# =========================================================================


# ---------------------------------------------------------------------------
# Read locale schemas
# ---------------------------------------------------------------------------


class DocumentLocaleReadSchema(BaseModel):
    """Base locale schema for GET responses.

    Extends the write schema with ``topic_id`` (Discourse forum topic).
    """

    lang: DefaultLangs
    version: Optional[int] = None
    title: Optional[str] = None
    description: Optional[str] = None
    summary: Optional[str] = None
    topic_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True, extra='ignore')


# ---------------------------------------------------------------------------
# Read geometry schemas  (one per document type family)
# ---------------------------------------------------------------------------
# The DB column ``geom`` is always ``POINT, dimension=2`` (srid=3857).
# ``geom_detail`` is unconstrained (GEOMETRY), but each doc type uses a
# specific sub-type.  We define one read schema per family so that the
# serialized shape exactly matches what the DB actually stores.
#
# All schemas set ``from_attributes=True`` for direct SA-instance reading.
# ``has_geom_detail`` is a computed column_property set by SQLAlchemy.


class PointGeometryReadSchema(BaseModel):
    """Read geometry for images, xreports, user profiles.

    Only a ``geom`` (POINT 2D) column — no ``geom_detail``.
    """

    version: Optional[int] = None
    geom: Optional[GeometryField.point_2d()] = None  # type: ignore[valid-type]  # noqa: E501
    has_geom_detail: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True, extra='ignore')


class WaypointGeometryReadSchema(BaseModel):
    """Read geometry for waypoints.

    Both ``geom`` and ``geom_detail`` are POINT 2D.
    """

    version: Optional[int] = None
    geom: Optional[GeometryField.point_2d()] = None  # type: ignore[valid-type]  # noqa: E501
    geom_detail: Optional[GeometryField.point_2d()] = None  # type: ignore[valid-type]  # noqa: E501
    has_geom_detail: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True, extra='ignore')


class LineGeometryReadSchema(BaseModel):
    """Read geometry for routes and outings.

    - ``geom``        — POINT 2D
    - ``geom_detail`` — LINESTRING / MULTILINESTRING, 2D–4D
    """

    version: Optional[int] = None
    geom: Optional[GeometryField.point_2d()] = None  # type: ignore[valid-type]  # noqa: E501
    geom_detail: Optional[GeometryField.line()] = None  # type: ignore[valid-type]  # noqa: E501
    has_geom_detail: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True, extra='ignore')


class PolygonGeometryReadSchema(BaseModel):
    """Read geometry for areas.

    ``geom_detail`` is POLYGON or MULTIPOLYGON, strictly 2D.
    """

    version: Optional[int] = None
    geom_detail: Optional[GeometryField.polygon()] = None  # type: ignore[valid-type]  # noqa: E501
    has_geom_detail: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True, extra='ignore')


class StrictPolygonGeometryReadSchema(BaseModel):
    """Read geometry for topo maps and coverages.

    ``geom_detail`` is POLYGON only, strictly 2D.
    """

    version: Optional[int] = None
    geom_detail: Optional[GeometryField.strict_polygon()] = None  # type: ignore[valid-type]  # noqa: E501
    has_geom_detail: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True, extra='ignore')


# ---------------------------------------------------------------------------
# Read association schemas
# ---------------------------------------------------------------------------


class AssociationDocRefSchema(BaseModel):
    """Minimal document reference in association listings."""

    document_id: int
    # Additional fields may be present depending on the document type;
    # ``extra = "allow"`` lets them through without strict typing.
    model_config = ConfigDict(from_attributes=True, extra='allow')


class RecentOutingsSchema(BaseModel):
    """Recent outings sub-block (``{'total': int, 'documents': [...]}``).

    Used by routes and waypoints to embed the last N associated outings.
    """

    total: int = 0
    documents: List[Any] = []

    model_config = ConfigDict(from_attributes=True, extra='ignore')


class AssociationsReadSchema(BaseModel):
    """Associations block as returned by GET responses.

    Unlike the write schema which only carries ``document_id`` refs,
    the read schema may contain richer objects with titles, etc.
    """

    users: Optional[List[AssociationDocRefSchema]] = None
    routes: Optional[List[AssociationDocRefSchema]] = None
    xreports: Optional[List[AssociationDocRefSchema]] = None
    waypoints: Optional[List[AssociationDocRefSchema]] = None
    waypoint_children: Optional[List[AssociationDocRefSchema]] = None
    books: Optional[List[AssociationDocRefSchema]] = None
    images: Optional[List[AssociationDocRefSchema]] = None
    articles: Optional[List[AssociationDocRefSchema]] = None
    outings: Optional[List[AssociationDocRefSchema]] = None
    areas: Optional[List[AssociationDocRefSchema]] = None
    coverages: Optional[List[AssociationDocRefSchema]] = None
    recent_outings: Optional[RecentOutingsSchema] = None

    model_config = ConfigDict(from_attributes=True, extra='ignore')


# ---------------------------------------------------------------------------
# Creator / author schema
# ---------------------------------------------------------------------------


class CreatorSchema(BaseModel):
    """Embedded creator/author info."""

    user_id: Optional[int] = None
    name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True, extra='allow')


# ---------------------------------------------------------------------------
# Base Read document schema
# ---------------------------------------------------------------------------


class DocumentReadSchema(BaseModel):
    """Base class for all ``*Read`` document schemas.

    Carries the fields that ``to_json_dict`` adds to every document type
    (``available_langs``, ``protected``, ``type``, ``areas``, etc.).
    Subclasses add document-type-specific columns, locales and geometry.
    """

    document_id: int
    version: Optional[int] = None
    quality: Optional[str] = None
    type: Optional[str] = None
    protected: Optional[bool] = None

    # populated by ``to_json_dict`` from attributes set on the SA object
    available_langs: Optional[List[str]] = None
    associations: Optional[AssociationsReadSchema] = None
    maps: Optional[List[Dict[str, Any]]] = None
    areas: Optional[List[Dict[str, Any]]] = None
    author: Optional[Any] = None
    creator: Optional[Any] = None
    name: Optional[str] = None
    forum_username: Optional[str] = None
    img_count: Optional[int] = None

    model_config = ConfigDict(from_attributes=True, extra='ignore')
