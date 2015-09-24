import collections
import datetime
from colander import null


def to_json_dict(obj, schema):
    return serialize(schema.dictify(obj))


def serialize(data):
    """
    Colanders `serialize` method is not intended for JSON serialization (it
    turns everything into a string and keeps colander.null).
    https://github.com/tisdall/cornice/blob/c18b873/cornice/schemas.py
    Returns the most agnostic version of specified data.
    (remove colander notions, datetimes in ISO, ...)
    """
    if isinstance(data, basestring):
        return unicode(data)
    if isinstance(data, collections.Mapping):
        return dict(map(serialize, data.iteritems()))
    if isinstance(data, collections.Iterable):
        return type(data)(map(serialize, data))
    if isinstance(data, (datetime.date, datetime.datetime)):
        return data.isoformat()
    if data is null:
        return None
    return data

# Validation functions


def validate_id(request):
    """Checks if a given id is an integer.
    """
    try:
        request.validated['id'] = int(request.matchdict['id'])
    except ValueError:
        request.errors.add('url', 'id', 'invalid id')
