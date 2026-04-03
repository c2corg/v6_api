"""
Lightweight ``FieldSpec`` objects for controlling serialisation.

A ``FieldSpec`` carries the SA model class (needed by ``objectify()``) and
three field-whitelists (needed by ``dictify()``).  It also supports a
``restrict()`` method that narrows the whitelists.
"""

from __future__ import annotations


def split_fields(all_fields):
    """Split a list of fields ([name, geometry.geom, locales.title, ...])
    into three lists depending on the prefix:

        fields: [name]
        geom_fields: [geom]
        locale_fields: [title]
    """
    geom_fields = []
    locale_fields = []
    fields = []

    for field in all_fields:
        if field.startswith('geometry'):
            geom_fields.append(field.replace('geometry.', ''))
        elif field.startswith('locales'):
            locale_fields.append(field.replace('locales.', ''))
        else:
            fields.append(field)

    return fields, geom_fields, locale_fields


class FieldSpec:
    """Describes which columns / locale-fields / geometry-fields are
    exposed for a given SA model.

    Parameters
    ----------
    sa_model : type
        The SQLAlchemy model class (e.g. ``Route``).
    columns : list[str]
        Top-level scalar/column field names.
    locale_fields : list[str] | None
        Locale sub-fields, or ``None`` if locales are absent.
    geometry_fields : list[str] | None
        Geometry sub-fields, or ``None`` if geometry is absent.
    """

    __slots__ = ('sa_model', 'columns', 'locale_fields', 'geometry_fields')

    def __init__(
        self,
        sa_model,
        columns,
        locale_fields=None,
        geometry_fields=None,
    ):
        self.sa_model = sa_model
        self.columns = list(columns)
        self.locale_fields = (
            list(locale_fields) if locale_fields is not None else None
        )
        self.geometry_fields = (
            list(geometry_fields) if geometry_fields is not None else None
        )

    # ------------------------------------------------------------------
    # restrict – replacement for schema_utils.restrict_schema
    # ------------------------------------------------------------------

    _default_columns = ['document_id', 'version', 'waypoint_type']
    _default_locale = ['version', 'lang']
    _default_geometry = ['version']

    def restrict(self, all_fields):
        """Return a *new* ``FieldSpec`` that only contains the given fields.

        *all_fields* uses the same dotted-prefix convention as the
        ``fields_*.py`` files::

            ['locales.title', 'geometry.geom', 'activities', ...]

        The result always includes default columns / locale / geometry
        fields (``document_id``, ``version``, ``lang``, …) for backward
        compatibility with the old ``restrict_schema`` behaviour.
        """
        fields, geom_fields, locale_fields = split_fields(all_fields)

        new_columns = [
            c for c in self.columns
            if c in fields or c in self._default_columns
        ]

        if self.locale_fields is not None:
            new_locale = [
                f for f in self.locale_fields
                if f in locale_fields or f in self._default_locale
            ]
        else:
            new_locale = None

        if self.geometry_fields is not None and geom_fields:
            new_geom = [
                f for f in self.geometry_fields
                if f in geom_fields or f in self._default_geometry
            ]
        else:
            new_geom = None

        return FieldSpec(
            sa_model=self.sa_model,
            columns=new_columns,
            locale_fields=new_locale,
            geometry_fields=new_geom,
        )

    # ------------------------------------------------------------------
    # conversion to the dict expected by dictify()
    # ------------------------------------------------------------------

    def to_dict(self):
        """Return the ``{columns, locales, geometry}`` dict consumed by
        :func:`c2corg_api.models.dictify.dictify`.
        """
        return {
            'columns': self.columns,
            'locales': self.locale_fields,
            'geometry': self.geometry_fields,
        }


def build_field_spec(
    sa_model,
    includes,
    locale_fields=None,
    geometry_fields=None,
):
    """Build a :class:`FieldSpec` from the same ``includes`` list that
    was used with ``SQLAlchemySchemaNode``.

    ``includes`` may contain ``'locales'`` and ``'geometry'`` entries;
    they are filtered out of the columns list.  The actual locale /
    geometry sub-fields are specified via *locale_fields* and
    *geometry_fields*.

    Parameters
    ----------
    sa_model : type
        The SQLAlchemy model class.
    includes : list[str]
        The combined whitelisted attribute names (may include
        ``'locales'`` and ``'geometry'``).
    locale_fields : list[str] | None
        Locale sub-fields.
    geometry_fields : list[str] | None
        Geometry sub-fields.  Typically
        ``document.geometry_attributes``.
    """
    columns = [c for c in includes if c not in ('locales', 'geometry')]
    return FieldSpec(
        sa_model=sa_model,
        columns=columns,
        locale_fields=locale_fields,
        geometry_fields=geometry_fields,
    )
