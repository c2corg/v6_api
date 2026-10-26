"""Field lists of the listing schemas (see `ModelSchema.restrict`)."""

default_fields_doc = ['document_id', 'version', 'waypoint_type']
default_fields_locale = ['version', 'lang']
default_fields_geometry = ['version']


def split_fields(all_fields):
    """Split a list of fields into three lists depending on the prefix.

    Split a list of fields ([name, geometry.geom, locales.title, ...]) into
    three lists depending on the prefix:

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
