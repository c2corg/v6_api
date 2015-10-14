from geoalchemy2 import WKBElement


def copy_attributes(obj_from, obj_to, attributes):
    """
    Copies the given attributes from `obj_from` to `obj_to` (shallow copy).
    """
    for attribute in attributes:
        if hasattr(obj_from, attribute):
            current_val = getattr(obj_to, attribute)
            new_val = getattr(obj_from, attribute)

            # To make the SQLAlchemy check if a document has changed work
            # properly, we only copy an attribute if the value has changed.
            # For geometries, we always copy the value.
            if isinstance(current_val, WKBElement) or \
                    isinstance(new_val, WKBElement) or \
                    current_val != new_val:
                setattr(obj_to, attribute, new_val)
