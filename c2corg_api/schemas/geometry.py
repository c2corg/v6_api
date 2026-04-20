"""
GeoJSON validation helpers for geometry Pydantic schemas.

These functions parse a GeoJSON string and verify:
1. It is valid JSON and a valid GeoJSON geometry object.
2. The geometry *type* is one of the allowed types
   (e.g. ``POINT``, ``LINESTRING``, ``POLYGON``, …).
3. Every coordinate has the expected number of dimensions
   (2 for 2D, 2-or-3 for 2D/3D, etc.).

The actual GeoJSON → WKBElement conversion is still performed later by
``_convert_geojson_to_wkb`` in the pydantic_validator module; these
helpers are pure *structural* validators executed inside Pydantic
``field_validator``s.

Serialization helpers
---------------------
``wkbelement_to_geojson_str``  — used by ``@field_serializer`` on Read
    schemas so that Pydantic can turn a ``WKBElement`` (from the DB) into a
    GeoJSON string when serializing an SA instance.

``geojson_str_to_wkbelement``  — used by ``@field_validator`` on write
    schemas (with ``mode='after'``) so that FastAPI can bind a validated
    GeoJSON string directly to the SA geometry column without a separate
    conversion step.  The SRID matches the PostGIS column definition
    (``srid=3857``).

Both helpers are thin wrappers over ``c2corg_api.ext.geometry`` which
contains the actual WKB ↔ GeoJSON logic.
"""

from __future__ import annotations

import json
import math
from typing import Any, FrozenSet, Optional, Sequence

import geojson as geojson_lib
from geoalchemy2 import WKBElement
from pydantic import GetCoreSchemaHandler
from pydantic_core import core_schema

# ---------------------------------------------------------------------------
# Dimension policies
# ---------------------------------------------------------------------------
# Each constant describes how many coordinate components are accepted.

DIM_2D: FrozenSet[int] = frozenset({2})
"""Strictly 2-dimensional coordinates (x, y)."""

DIM_2D_3D: FrozenSet[int] = frozenset({2, 3})
"""Accept both 2D and 3D coordinates (x, y or x, y, z)."""

DIM_2D_3D_4D: FrozenSet[int] = frozenset({2, 3, 4})
"""Accept 2D, 3D (Z) or 4D (ZM) coordinates."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _iter_coords(coordinates, depth: int):
    """Yield individual coordinate tuples from a nested GeoJSON coordinate
    structure.

    *depth* indicates the nesting level:
      - 0 → ``coordinates`` is a single position ``[x, y]``
      - 1 → list of positions (LineString, MultiPoint)
      - 2 → list of list of positions (Polygon, MultiLineString)
      - 3 → list of list of list of positions (MultiPolygon)
    """
    if depth == 0:
        yield coordinates
    else:
        for item in coordinates:
            yield from _iter_coords(item, depth - 1)


# GeoJSON type → nesting depth of the coordinates array
_COORD_DEPTH = {
    'POINT': 0,
    'MULTIPOINT': 1,
    'LINESTRING': 1,
    'MULTILINESTRING': 2,
    'POLYGON': 2,
    'MULTIPOLYGON': 3,
}


# ---------------------------------------------------------------------------
# Public validation function
# ---------------------------------------------------------------------------


def validate_geojson(
    value: Optional[str],
    *,
    allowed_types: Sequence[str],
    allowed_dims: FrozenSet[int] = DIM_2D_3D,
) -> Optional[str]:
    """Validate a GeoJSON geometry string.

    Parameters
    ----------
    value:
        The raw GeoJSON string from the request, or ``None``.
    allowed_types:
        Upper-cased geometry type names that are accepted
        (e.g. ``['POINT']``, ``['LINESTRING', 'MULTILINESTRING']``).
    allowed_dims:
        Set of acceptable coordinate component counts
        (e.g. ``DIM_2D`` for strictly 2D, ``DIM_2D_3D`` for 2D or 3D).

    Returns
    -------
    The original string unchanged (validation only; conversion to WKB
    happens downstream).

    Raises
    ------
    ValueError
        When the value is not valid GeoJSON, has the wrong geometry type,
        or has coordinates with the wrong number of dimensions.
    """
    if value is None:
        return value

    # -- 1. Parse JSON -------------------------------------------------------
    try:
        raw = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        raise ValueError(f'Invalid geometry: {value}')

    # -- 2. Must be a GeoJSON geometry object --------------------------------
    geo = geojson_lib.GeoJSON(raw)
    geom_type_raw = raw.get('type', '')
    geom_type = geom_type_raw.upper()

    if geom_type not in _COORD_DEPTH:
        raise ValueError(f'Invalid geometry: {value}')

    # -- 3. Check geometry type is allowed -----------------------------------
    allowed_upper = [t.upper() for t in allowed_types]
    if geom_type not in allowed_upper:
        raise ValueError(
            f'Invalid geometry type. '
            f'Expected: {allowed_upper}. Got: {geom_type_raw.upper()}.'
        )

    # -- 4. Validity check (e.g. self-intersecting polygons) -----------------
    try:
        if not geo.is_valid:
            raise ValueError(f'Invalid geometry: {value}')
    except ValueError:
        raise
    except Exception:
        raise ValueError(f'Invalid geometry: {value}')

    # -- 5. Check coordinate dimensions --------------------------------------
    coordinates = raw.get('coordinates')
    if coordinates is None:
        raise ValueError(f'Invalid geometry: {value}')

    depth = _COORD_DEPTH[geom_type]
    for coord in _iter_coords(coordinates, depth):
        if not isinstance(coord, (list, tuple)):
            raise ValueError(f'Invalid geometry: {value}')
        # Each coordinate must be a flat array of numbers.
        # Deeply-nested / malformed coordinates (e.g. [[[x, y]]])
        # will have non-numeric elements at this level.
        if not all(isinstance(c, (int, float)) for c in coord):
            raise ValueError(f'Invalid geometry: {value}')
        # Reject NaN / Inf — not valid in GeoJSON.
        if any(
            isinstance(c, float) and (math.isnan(c) or math.isinf(c)) for c in coord
        ):
            raise ValueError(f'Invalid geometry: {value}')
        n = len(coord)
        if n not in allowed_dims:
            dims_label = '/'.join(
                {2: '2D', 3: '3D (Z)', 4: '4D (ZM)'}.get(d, f'{d}D')
                for d in sorted(allowed_dims)
            )
            raise ValueError(
                f'Expected {dims_label} coordinates '
                f'({sorted(allowed_dims)} components), got {n}.'
            )

    return value


# ---------------------------------------------------------------------------
# WKBElement ↔ GeoJSON string helpers (for Pydantic @field_serializer /
# @field_validator on Read and Write schemas)
# ---------------------------------------------------------------------------

# SRID used by every geometry column in this project.
_GEOM_SRID = 3857


def wkbelement_to_geojson_str(value: Any) -> Optional[str]:
    """Convert a ``WKBElement`` (from the DB) to a 2D GeoJSON string.

    Used as a Pydantic ``@field_serializer`` on ``GeometryReadSchema`` so
    that SA instances can be serialized directly to JSON without going
    through ``dictify``.

    Returns ``None`` if *value* is already ``None``.  Passes strings
    through unchanged (e.g. when the value was already serialized in a
    test or during a round-trip).

    Raises ``ValueError`` for unrecognised types so Pydantic surfaces a
    clear error rather than a silent ``None``.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value  # already a GeoJSON string (e.g. in tests)
    if isinstance(value, WKBElement):
        from c2corg_api.ext.geometry import geojson_from_wkbelement

        return geojson_from_wkbelement(value)
    raise ValueError(f'Cannot serialize geometry value of type {type(value).__name__}')


def geojson_str_to_wkbelement(value: Any) -> Optional[WKBElement]:
    """Convert a validated GeoJSON string to a ``WKBElement``.

    Used as a Pydantic ``@field_validator`` (``mode='after'``) on write
    geometry schemas so that FastAPI can bind the geometry field directly
    to the SA model without a separate conversion step.

    The SRID is fixed at ``3857`` to match the PostGIS column definition.

    Passes ``WKBElement`` values through unchanged (idempotent).
    Returns ``None`` if *value* is ``None``.
    """
    if value is None:
        return None
    if isinstance(value, WKBElement):
        return value  # already converted (e.g. nested validator call)
    if isinstance(value, str):
        try:
            raw = json.loads(value)
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError(f'Invalid GeoJSON string: {exc}') from exc
        from c2corg_api.ext.geometry import wkbelement_from_geojson

        return wkbelement_from_geojson(raw, srid=_GEOM_SRID)
    raise ValueError(
        f'Cannot deserialize geometry value of type {type(value).__name__}'
    )


# ---------------------------------------------------------------------------
# GeometryField — parameterized custom Pydantic type
# ---------------------------------------------------------------------------
# A single type that handles both WKBElement ↔ GeoJSON string conversion
# automatically, with type and dimension constraints baked in per field.
#
# Named constructors cover every geometry usage in this project:
#
#   GeometryField.point()          POINT            2D or 3D
#   GeometryField.point_2d()       POINT            strictly 2D
#   GeometryField.line()           LINE/MULTILINE   2D, 3D, or 4D
#   GeometryField.polygon()        POLYGON/MULTI    2D or 3D
#   GeometryField.strict_polygon() POLYGON only     strictly 2D
#
# Read schemas (from_attributes=True) also use these same types — Pydantic
# calls _validate() when reading from an SA instance and _serialize() when
# producing JSON, so no separate ``@field_serializer`` is needed.
#
# Serialization note
# ------------------
# ``geojson_from_wkbelement`` in ext/geometry.py faithfully preserves all
# dimensions stored in the DB (2D, 3D, 4D).  The 2D-stripping that happens
# in ``wkb_to_shape()`` is only for internal Shapely operations
# (midpoint, equality checks) — it is NOT applied here.
# Responses therefore mirror what is stored in the DB.
# ---------------------------------------------------------------------------

# Cache to avoid creating duplicate classes for the same constraints
# (keeps Pydantic's schema cache consistent).
_FIELD_CACHE: dict = {}


class GeometryField:
    """Parameterized Pydantic type for PostGIS geometry columns.

    Converts automatically between GeoJSON strings (wire format) and
    ``WKBElement`` instances (SQLAlchemy / PostGIS).

    Use one of the named constructors as the field annotation::

        geom:        Optional[GeometryField.point()]          = None
        geom_detail: Optional[GeometryField.point_2d()]       = None
        geom_detail: Optional[GeometryField.line()]           = None
        geom_detail: Optional[GeometryField.polygon()]        = None
        geom_detail: Optional[GeometryField.strict_polygon()] = None

    Deserialize (JSON str → WKBElement):
        ``validate_geojson`` checks type and dimensions first, then the
        string is converted to a ``WKBElement``.  ``WKBElement`` values pass
        through unchanged (idempotent for SA read path).

    Serialize (WKBElement → GeoJSON str):
        ``geojson_from_wkbelement`` is called automatically by Pydantic when
        ``model_dump(mode='json')`` or a FastAPI response is produced.
        Dimensions are preserved faithfully (2D/3D/4D — whatever the DB has).
    """

    @classmethod
    def _make(cls, allowed_types: Sequence[str], allowed_dims: FrozenSet[int]) -> type:
        """Return a unique class whose core schema enforces the given
        *allowed_types* and *allowed_dims*."""
        key = (tuple(allowed_types), frozenset(allowed_dims))
        if key in _FIELD_CACHE:
            return _FIELD_CACHE[key]

        # Build a stable, human-readable class name for debugging / repr.
        type_label = '_'.join(t.capitalize() for t in allowed_types)
        dims_label = '_'.join(str(d) for d in sorted(allowed_dims))
        klass_name = f'GeometryField_{type_label}_{dims_label}D'

        # Close over the constraints.
        _allowed_types = list(allowed_types)
        _allowed_dims = frozenset(allowed_dims)

        def _validate(value: Any) -> Optional[WKBElement]:
            """GeoJSON str / WKBElement / None → WKBElement (or None)."""
            if value is None:
                return None
            if isinstance(value, WKBElement):
                return value  # SA read path — already the right type
            if isinstance(value, str):
                # Step 1: structural validation (type + dims)
                validate_geojson(
                    value, allowed_types=_allowed_types, allowed_dims=_allowed_dims
                )
                # Step 2: convert to WKBElement (SRID 3857)
                return geojson_str_to_wkbelement(value)
            raise ValueError(
                f'Cannot deserialize geometry value of type {type(value).__name__}'
            )

        def _serialize(value: Any) -> Optional[str]:
            """WKBElement / str / None → GeoJSON str (or None)."""
            return wkbelement_to_geojson_str(value)

        def __get_pydantic_core_schema__(  # noqa: N807
            cls_inner: Any, source_type: Any, handler: GetCoreSchemaHandler
        ) -> core_schema.CoreSchema:
            return core_schema.no_info_plain_validator_function(
                _validate,
                serialization=core_schema.plain_serializer_function_ser_schema(
                    _serialize,
                    info_arg=False,
                    return_schema=core_schema.nullable_schema(core_schema.str_schema()),
                ),
            )

        klass = type(
            klass_name,
            (),
            {'__get_pydantic_core_schema__': classmethod(__get_pydantic_core_schema__)},
        )
        _FIELD_CACHE[key] = klass
        return klass

    # ------------------------------------------------------------------
    # Named constructors — one per geometry usage in this project.
    # ------------------------------------------------------------------

    @classmethod
    def point(cls) -> type:
        """POINT, 2D or 3D.

        Used by waypoint ``geom`` / ``geom_detail``,
        route/outing ``geom``, image, xreport, user-profile ``geom``.
        """
        return cls._make(['POINT'], DIM_2D_3D)

    @classmethod
    def point_2d(cls) -> type:
        """POINT, strictly 2D only.

        Used when the DB column is declared ``POINT, dimension=2``
        and no Z coordinate is expected or accepted.
        """
        return cls._make(['POINT'], DIM_2D)

    @classmethod
    def line(cls) -> type:
        """LINESTRING or MULTILINESTRING, 2D, 3D, or 4D.

        Used by route/outing ``geom_detail``.  GPS tracks may carry
        elevation (Z) and timestamps (M), so all four dimensions are
        accepted on the way in.  The DB stores them faithfully.
        """
        return cls._make(['LINESTRING', 'MULTILINESTRING'], DIM_2D_3D_4D)

    @classmethod
    def polygon(cls) -> type:
        """POLYGON or MULTIPOLYGON, strictly 2D.

        Used by area ``geom_detail``.  Area boundaries are always 2D.
        """
        return cls._make(['POLYGON', 'MULTIPOLYGON'], DIM_2D)

    @classmethod
    def strict_polygon(cls) -> type:
        """POLYGON only, strictly 2D.

        Used by topo-map and coverage ``geom_detail``.
        """
        return cls._make(['POLYGON'], DIM_2D)
