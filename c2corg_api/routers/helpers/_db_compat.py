"""
Transitional helper for the DBSession → explicit ``db`` migration.

Import ``resolve_db`` from here instead of duplicating the fallback
logic in every module.  Once all callers pass ``db`` explicitly this
module can be deleted.
"""


def resolve_db(db):
    """Return *db* if not None, else fall back to the legacy DBSession."""
    if db is not None:
        return db
    from c2corg_api.models import DBSession

    return DBSession
