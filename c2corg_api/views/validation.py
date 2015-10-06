from colander import null

# Validation functions


def validate_id(request):
    """Checks if a given id is an integer.
    """
    try:
        request.validated['id'] = int(request.matchdict['id'])
    except ValueError:
        request.errors.add('url', 'id', 'invalid id')


def is_missing(val):
    return val is None or val == '' or val == [] or val is null


def check_required_fields(document, fields, request, updating):
    """Checks that the given fields are set on the document.
    """

    for field in fields:
        if '.' not in field:
            if updating and field in ['geometry', 'locales']:
                # when updating geometry and locales may be empty
                continue
            if is_missing(document.get(field)):
                request.errors.add('body', field, 'Required')
        else:
            # fields like 'geometry.geom'
            if field in ['locales.title']:
                # this is a required field for all documents, which is already
                # checked when validating against the Colander schema
                pass
            else:
                field_parts = field.split('.')
                attr = document.get(field_parts[0])
                if attr:
                    if is_missing(attr.get(field_parts[1])):
                        request.errors.add('body', field, 'Required')


def check_duplicate_locales(document, request):
    """Check that there is only one entry for each culture.
    """
    locales = document.get('locales')
    if locales:
        cultures = set()
        for locale in locales:
            culture = locale.get('culture')
            if culture in cultures:
                request.errors.add(
                    'body', 'locales',
                    'culture "%s" is given twice' % (culture))
                return
            cultures.add(culture)


def check_get_for_integer_property(request, key, required):
    """Checks if the value associated to a given key is an integer.
    """
    if not required and request.GET.get(key) is None:
        return

    try:
        request.validated[key] = int(request.GET.get(key))
    except ValueError:
        request.errors.add('url', key, 'invalid ' + key)


def validate_pagination(request):
    """
    Checks if a given optional offset is an integer,
    if a given optional total is an integer,
    if a given optional limit is an integer,
    if a given optional after is an integer
    """
    check_get_for_integer_property(request, 'offset', False)
    check_get_for_integer_property(request, 'total', False)
    check_get_for_integer_property(request, 'limit', False)
    check_get_for_integer_property(request, 'after', False)
