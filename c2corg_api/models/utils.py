def copy_attributes(obj_from, obj_to, attributes):
    """
    Copies the given attributes from `obj_from` to `obj_to` (shallow copy).
    """
    for attribute in attributes:
        if hasattr(obj_from, attribute):
            val = getattr(obj_from, attribute)
            setattr(obj_to, attribute, val)
