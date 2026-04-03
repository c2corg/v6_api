"""
Standalone ``dictify()`` implementation.

Converts a SQLAlchemy model instance into a plain dict using
:class:`~c2corg_api.models.field_spec.FieldSpec` whitelists so that
the output matches the current JSON API contract byte-for-byte.
"""
import collections.abc
import datetime
import logging

from geoalchemy2 import WKBElement

from c2corg_api.ext.geometry import geojson_from_wkbelement

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# dictify  (schema-free)
# ---------------------------------------------------------------------------

def dictify(instance, field_spec):
    """Convert a SQLAlchemy *instance* into a JSON-ready dict.

    *field_spec* may be:

    * a :class:`~c2corg_api.models.field_spec.FieldSpec` instance, or
    * a plain ``dict`` with keys ``columns``, ``locales``, ``geometry``.

    The output is fully serialised: ``WKBElement`` → GeoJSON string,
    ``datetime`` → ISO-8601 string, ``None`` is preserved as ``None``.
    """
    if hasattr(field_spec, 'to_dict'):
        field_spec = field_spec.to_dict()

    result = {}

    # 1. Scalar / column attributes
    for col in field_spec['columns']:
        value = getattr(instance, col, None)
        result[col] = _serialize_value(value)

    # 2. Locales (one-to-many relationship)
    locale_fields = field_spec.get('locales')
    if locale_fields is not None and hasattr(instance, 'locales'):
        locales_list = getattr(instance, 'locales', None) or []
        result['locales'] = [
            _dictify_child(loc, locale_fields)
            for loc in locales_list
        ]

    # 3. Geometry (one-to-one relationship)
    geom_fields = field_spec.get('geometry')
    if geom_fields is not None and hasattr(instance, 'geometry'):
        geom = getattr(instance, 'geometry', None)
        if geom is None:
            result['geometry'] = None
        else:
            result['geometry'] = _dictify_child(geom, geom_fields)

    return result


def _dictify_child(instance, field_names):
    """Dictify a related object (locale or geometry) using a flat
    list of field names.
    """
    result = {}
    for name in field_names:
        value = getattr(instance, name, None)
        result[name] = _serialize_value(value)
    return result


def _serialize_value(value):
    """Convert a single value to its JSON-friendly form."""
    if value is None:
        return None
    if isinstance(value, WKBElement):
        return geojson_from_wkbelement(value)
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, str):
        return value
    if isinstance(value, collections.abc.Mapping):
        return {k: _serialize_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize_value(v) for v in value]
    return value
