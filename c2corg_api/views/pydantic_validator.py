"""
Pydantic-based body validator for cornice views.

This module provides a drop-in replacement for cornice's
`colander_body_validator`, using pydantic models instead of colander schemas.

Usage:
    from c2corg_api.views.pydantic_validator import make_pydantic_validator

    @restricted_json_view(
        validators=[make_pydantic_validator(MyPydanticModel), validate_id])
    def put(self):
        ...
"""
import json
import logging
import typing

import geojson as geojson_lib
from geoalchemy2 import WKBElement
from pydantic import BaseModel, ValidationError

from c2corg_api.ext.colander_ext import wkbelement_from_geojson

log = logging.getLogger(__name__)

# The default SRID used by the application for point geometries.
_DEFAULT_SRID = 3857

# Geometry fields that may contain GeoJSON strings which need to be
# converted to WKBElement so that downstream SQLAlchemy code works.
_GEOM_FIELDS = ('geom', 'geom_detail')


def _convert_geojson_to_wkb(data, srid=_DEFAULT_SRID, request=None,
                            allowed_geometry_types=None,
                            field_prefix=None):
    """Walk *data* (a nested dict) and convert any geometry GeoJSON strings
    found under ``geometry.geom`` / ``geometry.geom_detail`` into
    :class:`WKBElement` instances, matching what colander's ``deserialize``
    used to do.

    If *request* is given, invalid geometries are reported via
    ``request.errors`` instead of being silently ignored.

    *allowed_geometry_types* is an optional list of upper-case geometry type
    strings (e.g. ``['LINESTRING', 'MULTILINESTRING']``) that restrict which
    GeoJSON types are accepted for ``geom_detail``.

    *field_prefix* is an optional string prepended to error field names
    (e.g. ``'images.0'`` → ``'images.0.geometry.geom'``).
    """
    if not isinstance(data, dict):
        return

    def _field_path(field):
        path = 'geometry.%s' % field
        if field_prefix:
            path = '%s.%s' % (field_prefix, path)
        return path

    geometry = data.get('geometry')
    if geometry:
        for field in _GEOM_FIELDS:
            value = geometry.get(field)
            if not value or isinstance(value, WKBElement):
                continue
            try:
                geo = geojson_lib.loads(value)
                if not isinstance(geo, geojson_lib.GeoJSON):
                    raise ValueError('not a GeoJSON object')
                if not _is_valid_geojson(geo):
                    raise ValueError('invalid geometry')
                # Check geometry type constraints.
                # ``geom`` is always a POINT column in the DB, so reject
                # non-POINT geometries for it unconditionally.
                # ``geom_detail`` is typed by *allowed_geometry_types*
                # when provided (routes accept LINESTRING/MULTILINESTRING,
                # areas accept POLYGON/MULTIPOLYGON, etc.).
                check_types = None
                if field == 'geom':
                    check_types = ['POINT']
                elif field == 'geom_detail' and allowed_geometry_types:
                    check_types = allowed_geometry_types

                if check_types:
                    geom_type = geo.get('type', '').upper()
                    if geom_type not in check_types:
                        if request is not None:
                            request.errors.add(
                                'body', _field_path(field),
                                'Invalid geometry type. Expected: %s. '
                                'Got: %s.' % (
                                    check_types,
                                    geo.get('type', '').upper()))
                        continue
                geometry[field] = wkbelement_from_geojson(geo, srid)
            except Exception:
                if request is not None:
                    request.errors.add(
                        'body', _field_path(field),
                        'Invalid geometry: %s' % value)
                # Leave as-is when no request context is available.

    # Also walk nested 'document' key (for update schemas that
    # wrap the doc).
    doc = data.get('document')
    if doc:
        _convert_geojson_to_wkb(doc, srid, request=request,
                                allowed_geometry_types=allowed_geometry_types)


def _is_valid_geojson(geo):
    """Return True if the parsed GeoJSON object represents a valid geometry."""
    try:
        return geo.is_valid
    except Exception:
        return False


def _is_collection_field(model, field_name):
    """Return True if *field_name* on *model* is a list, dict, or
    BaseModel type (i.e. a relationship / nested object).

    These are the fields whose ``None`` values must be stripped before
    the dict reaches ColanderAlchemy's ``objectify``, which would try
    to iterate over them.
    """
    field_info = model.model_fields.get(field_name)
    if field_info is None:
        return False
    annotation = field_info.annotation
    # Unwrap Optional[X] → X
    origin = typing.get_origin(annotation)
    if origin is typing.Union:
        args = [a for a in typing.get_args(annotation)
                if a is not type(None)]
        if args:
            annotation = args[0]
            origin = typing.get_origin(annotation)
    # list[…], dict[…], List[…], Dict[…]
    if origin in (list, dict):
        return True
    # A nested pydantic model
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return True
    return False


def _collect_fields_set(instance):
    """Walk a pydantic model instance and return a nested structure that
    records which fields were explicitly set (present in the request body)
    at each level.

    Returns a dict mapping field names to either ``True`` (scalar field
    that was set) or a nested ``_collect_fields_set`` result (for
    BaseModel sub-fields).
    """
    result = {}
    for name in instance.model_fields_set:
        value = getattr(instance, name, None)
        if isinstance(value, BaseModel):
            result[name] = _collect_fields_set(value)
        else:
            result[name] = True
    return result


def _strip_defaults_and_collections(data, fields_set, model):
    """Remove unneeded ``None`` values from *data*.

    - Collection fields (list, dict, nested BaseModel) whose value is
      ``None`` are always stripped so that ColanderAlchemy's ``objectify``
      does not try to iterate over them.

    - Scalar fields whose value is ``None`` **and** that were not
      explicitly provided in the request body (i.e. not in *fields_set*)
      are stripped so that ``objectify`` does not overwrite non-nullable
      DB columns with ``NULL``.

    *fields_set* is either a ``set`` of field names (for the top level)
    or a dict produced by :func:`_collect_fields_set` (for nested models).
    """
    result = {}
    for key, value in data.items():
        field_info = model.model_fields.get(key)

        # Determine whether this key was explicitly sent by the user.
        if isinstance(fields_set, dict):
            key_was_set = key in fields_set
        else:
            key_was_set = key in fields_set

        if value is None and field_info is not None:
            if _is_collection_field(model, key):
                continue  # always strip None collections
            if not key_was_set:
                continue  # strip defaulted-None scalars not sent by user

        # Recurse into nested BaseModel dicts
        if isinstance(value, dict) and field_info is not None:
            inner_model = _unwrap_annotation(field_info.annotation)
            if (isinstance(inner_model, type)
                    and issubclass(inner_model, BaseModel)):
                # Use the nested fields_set info if available
                if isinstance(fields_set, dict) and isinstance(
                        fields_set.get(key), dict):
                    nested_fs = fields_set[key]
                else:
                    nested_fs = set(value.keys())
                value = _strip_defaults_and_collections(
                    value, nested_fs, inner_model)
        result[key] = value
    return result
    return result


def _unwrap_annotation(annotation):
    """Unwrap ``Optional[X]`` to ``X``."""
    origin = typing.get_origin(annotation)
    if origin is typing.Union:
        args = [a for a in typing.get_args(annotation)
                if a is not type(None)]
        if args:
            return args[0]
    return annotation


def make_pydantic_validator(pydantic_model, allowed_geometry_types=None,
                            strip_defaults=True):
    """Create a cornice validator that validates the request body against
    the given pydantic model.

    On success, the validated data is merged into ``request.validated``.
    On failure, structured errors are added to ``request.errors``.

    *allowed_geometry_types* is an optional list of upper-case geometry type
    strings (e.g. ``['LINESTRING', 'MULTILINESTRING']``) passed through to
    the GeoJSON → WKB conversion so that incorrect types are rejected.

    *strip_defaults* controls whether unset ``None`` scalar fields are
    removed from the validated dict.  Defaults to ``True`` which is
    required for document schemas that go through ColanderAlchemy's
    ``objectify``.  Set to ``False`` for simple hand-written schemas
    where downstream code expects all fields to be present.
    """

    def pydantic_body_validator(request, **kwargs):
        try:
            body = request.json_body
        except (json.JSONDecodeError, ValueError):
            body = {}

        try:
            validated = pydantic_model.model_validate(body)
        except ValidationError as exc:
            for error in exc.errors():
                # Build a dotted field path from pydantic's loc tuple
                location = '.'.join(
                    str(part) for part in error['loc'])
                request.errors.add(
                    'body', location, error['msg'])
            request.errors.status = 400
            return

        # Merge the validated dict into request.validated so that
        # downstream code (e.g. _put) can use it as before.
        #
        # We dump *all* fields (including None scalars) so that the
        # resulting dict is truthy even when the request body was
        # almost empty – downstream validators like
        # ``make_validator_create`` gate on ``if document:`` and an
        # empty dict would skip required-field checks.
        #
        # However, None values for list/dict fields (locales,
        # associations, geometry …) must be stripped because
        # ColanderAlchemy's ``objectify`` tries to iterate over them.
        #
        # Additionally, None values for scalar fields that the user
        # did NOT explicitly send must be stripped so that
        # ``objectify`` does not set non-nullable DB columns to NULL.
        if strip_defaults:
            nested_fields_set = _collect_fields_set(validated)
            dumped = _strip_defaults_and_collections(
                validated.model_dump(), nested_fields_set,
                pydantic_model)
        else:
            dumped = validated.model_dump()

        # Convert GeoJSON geometry strings -> WKBElement, replicating
        # what the colander schema ``deserialize`` used to do.
        _convert_geojson_to_wkb(
            dumped, request=request,
            allowed_geometry_types=allowed_geometry_types)

        request.validated.update(dumped)

    return pydantic_body_validator
