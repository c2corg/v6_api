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


def _convert_geojson_to_wkb(data, srid=_DEFAULT_SRID):
    """Walk *data* (a nested dict) and convert any geometry GeoJSON strings
    found under ``geometry.geom`` / ``geometry.geom_detail`` into
    :class:`WKBElement` instances, matching what colander's ``deserialize``
    used to do.
    """
    if not isinstance(data, dict):
        return

    geometry = data.get('geometry')
    if geometry:
        for field in _GEOM_FIELDS:
            value = geometry.get(field)
            if not value or isinstance(value, WKBElement):
                continue
            try:
                geo = geojson_lib.loads(value)
                if isinstance(geo, geojson_lib.GeoJSON):
                    geometry[field] = wkbelement_from_geojson(
                        geo, srid)
            except Exception:
                # Leave as-is; validation errors will surface later.
                pass

    # Also walk nested 'document' key (for update schemas that
    # wrap the doc).
    doc = data.get('document')
    if doc:
        _convert_geojson_to_wkb(doc, srid)


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


def _strip_none_collections(data, model):
    """Remove ``None``-valued keys from *data* when the corresponding
    field on *model* is a list, dict, or nested ``BaseModel``.

    Scalar ``None`` values are preserved so that the dict stays truthy
    and downstream validators (``check_required_fields``) can detect
    missing fields.

    Recurses into nested dicts whose corresponding field is a
    ``BaseModel`` subclass.
    """
    result = {}
    for key, value in data.items():
        field_info = model.model_fields.get(key)
        if value is None and field_info is not None:
            if _is_collection_field(model, key):
                continue  # strip None list / nested-model fields
        # Recurse into nested BaseModel dicts
        if (isinstance(value, dict) and field_info is not None):
            inner_model = _unwrap_annotation(field_info.annotation)
            if (isinstance(inner_model, type)
                    and issubclass(inner_model, BaseModel)):
                value = _strip_none_collections(value, inner_model)
        result[key] = value
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


def make_pydantic_validator(pydantic_model):
    """Create a cornice validator that validates the request body against
    the given pydantic model.

    On success, the validated data is merged into ``request.validated``.
    On failure, structured errors are added to ``request.errors``.
    """

    def pydantic_body_validator(request, **kwargs):
        try:
            body = request.json_body
        except (json.JSONDecodeError, ValueError):
            request.errors.add('body', '', 'Invalid JSON body')
            request.errors.status = 400
            return

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
        dumped = _strip_none_collections(
            validated.model_dump(), pydantic_model)

        # Convert GeoJSON geometry strings -> WKBElement, replicating
        # what the colander schema ``deserialize`` used to do.
        _convert_geojson_to_wkb(dumped)

        request.validated.update(dumped)

    return pydantic_body_validator
