default_fields_doc = ['document_id', 'version', 'waypoint_type']
default_fields_locale = ['version', 'lang']
default_fields_geometry = ['version']


def restrict_schema(base_schema, all_fields):
    """Create a new schema from an existing one with only the
    given fields.
    """
    fields, geom_fields, locale_fields = split_fields(all_fields)

    schema = base_schema.clone()
    children = []
    for node in schema.children:
        if node.name == 'geometry':
            if geom_fields:
                children.append(node)
                filter_node(node, geom_fields, default_fields_geometry)
        elif node.name == 'locales':
            children.append(node)
            locale_node = node.children[0]
            filter_node(locale_node, locale_fields, default_fields_locale)
        else:
            if node.name in fields or node.name in default_fields_doc:
                children.append(node)

    schema.children = children

    return schema


def split_fields(all_fields):
    """Split a list of fields ([name, geometry.geom, locales.title, ...]) into
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


def filter_node(node, fields, default_fields):
    children = []
    for child_node in node.children:
        if child_node.name in fields or child_node.name in default_fields:
            children.append(child_node)
    node.children = children
