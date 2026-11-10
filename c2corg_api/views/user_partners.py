from sqlalchemy import func

from c2corg_api import DBSession
from c2corg_api.models.association import Association
from c2corg_api.models.common.document_types import OUTING_TYPE, USERPROFILE_TYPE
from c2corg_api.models.outing import Outing
from c2corg_api.views.document_listings import get_documents_for_ids
from c2corg_api.views.document_schemas import user_profile_documents_config

# the outings of the user that are looked at, the most recent first
RECENT_OUTINGS = 20
# the partners returned at most
MAX_PARTNERS = 8


def get_recent_partner_ids(user_id, outings=RECENT_OUTINGS, limit=MAX_PARTNERS):
    """Return the ids of the users of the recent outings of a user."""
    # the latest outings of the user, by their end date
    recent_outings = (
        DBSession.query(Outing.document_id.label('outing_id'), Outing.date_end)
        .join(Association, Association.child_document_id == Outing.document_id)
        .filter(Association.parent_document_id == user_id)
        .filter(Association.parent_document_type == USERPROFILE_TYPE)
        .filter(Association.child_document_type == OUTING_TYPE)
        .filter(Outing.redirects_to.is_(None))
        .order_by(Outing.date_end.desc(), Outing.document_id.desc())
        .limit(outings)
        .subquery()
    )

    # the other users of these outings: the one of the latest outing first,
    # then the one with the most outings together
    last_outing = func.max(recent_outings.c.date_end)
    shared_outings = func.count(recent_outings.c.outing_id)
    rows = (
        DBSession.query(Association.parent_document_id)
        .join(
            recent_outings,
            Association.child_document_id == recent_outings.c.outing_id,
        )
        .filter(Association.parent_document_type == USERPROFILE_TYPE)
        .filter(Association.parent_document_id != user_id)
        .group_by(Association.parent_document_id)
        .order_by(
            last_outing.desc(),
            shared_outings.desc(),
            Association.parent_document_id,
        )
        .limit(limit)
        .all()
    )
    return [partner_id for (partner_id,) in rows]


def read_partners(request):
    """Get the users of the recent outings of the authenticated user.

    Request:
        `GET` `/users/partners`

    Example response:

        {
            'partners': [
                {
                    'document_id': 123,
                    ...
                }
            ]
        }
    """
    partner_ids = get_recent_partner_ids(request.authenticated_userid)
    # the listing keeps the order of the ids
    partners = get_documents_for_ids(
        partner_ids, None, user_profile_documents_config
    ).get('documents')
    return {'partners': partners}
