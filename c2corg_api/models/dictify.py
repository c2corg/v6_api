"""
Standalone replacement for ColanderAlchemy's ``dictify()`` method.

Converts a SQLAlchemy model instance into a plain dict, using a
field-whitelist extracted from the existing ColanderAlchemy schemas so
that the output matches the current JSON API contract byte-for-byte.

This module eliminates the runtime dependency on ColanderAlchemy for the
GET / serialisation code paths.
"""
import collections.abc
import datetime
import logging

from geoalchemy2 import WKBElement

from c2corg_api.ext.colander_ext import geojson_from_wkbelement

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Field-spec extraction (bridge to the existing ColanderAlchemy schemas)
# ---------------------------------------------------------------------------

def fields_from_schema(schema):
    """Extract a ``FieldSpec`` from a ColanderAlchemy schema node.

    A ``FieldSpec`` is a plain dict that mirrors the schema's three-level
    whitelist::

        {
            'columns': ['document_id', 'version', 'quality', ...],
            'locales': ['version', 'lang', 'title', ...] or None,
            'geometry': ['version', 'geom', 'geom_detail'] or None,
        }

    When ``locales`` or ``geometry`` is ``None`` the relationship is not
    present in the schema and will be omitted from the output.
    """
    columns = []
    locales = None
    geometry = None

    inspector = getattr(schema, 'inspector', None)

    for child in schema:
        name = child.name

        # Is it a relationship?
        is_rel = False
        if inspector is not None:
            try:
                getattr(inspector.relationships, name)
                is_rel = True
            except AttributeError:
                pass

        if name == 'locales' and is_rel:
            # The locale sub-schema is always the first (and only) child
            # of the Sequence node.
            locale_schema = child.children[0]
            locales = [c.name for c in locale_schema]
        elif name == 'geometry' and is_rel:
            geometry = [c.name for c in child]
        else:
            columns.append(name)

    return {
        'columns': columns,
        'locales': locales,
        'geometry': geometry,
    }


# ---------------------------------------------------------------------------
# dictify  (schema-free)
# ---------------------------------------------------------------------------

def dictify(instance, field_spec):
    """Convert a SQLAlchemy *instance* into a JSON-ready dict.

    *field_spec* is a dict as returned by :func:`fields_from_schema`
    (or hand-crafted) that controls which fields appear in the output.

    The output is fully serialised: ``WKBElement`` → GeoJSON string,
    ``datetime`` → ISO-8601 string, ``None`` is preserved as ``None``.
    """
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
            _dictify_child(loc, locale_fields) for loc in locales_list
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
