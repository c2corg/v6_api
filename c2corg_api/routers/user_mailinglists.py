"""
FastAPI User Mailinglists router.

Mirrors ``c2corg_api.views.user_mailinglists``.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from c2corg_api.database import get_db
from c2corg_api.models.common.attributes import Mailinglists
from c2corg_api.models.mailinglist import Mailinglist
from c2corg_api.models.user import User
from c2corg_api.security.fastapi_security import get_current_user

log = logging.getLogger(__name__)

router = APIRouter(prefix='/v2/users', tags=['user-mailinglists'])


def _validate_mailinglist_statuses(data: dict):
    errors = []
    mailinglists = {}
    for ml in data:
        if ml not in Mailinglists:
            errors.append(
                {
                    'location': 'body',
                    'name': ml,
                    'description': ('Mailing list `{}` does not exist'.format(ml)),
                }
            )
        elif not isinstance(data[ml], bool):
            errors.append(
                {
                    'location': 'body',
                    'name': ml,
                    'description': (
                        'Status `{}` of mailing list `{}` should be boolean'.format(
                            data[ml], ml
                        )
                    ),
                }
            )
        else:
            mailinglists[ml] = data[ml]
    return mailinglists, errors


@router.get('/mailinglists')
def get_mailinglists(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    res = db.query(Mailinglist.listname).filter(Mailinglist.user_id == user.id).all()
    subscribed = [row[0] for row in res]
    return {ml: ml in subscribed for ml in Mailinglists}


@router.post('/mailinglists')
async def update_mailinglists(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data = await request.json()
    mailinglists, errors = _validate_mailinglist_statuses(data)
    if errors:
        raise HTTPException(
            status_code=400, detail={'status': 'error', 'errors': errors}
        )

    loaded_user = db.get(User, user.id)

    subscribed_lists = (
        db.query(Mailinglist).filter(Mailinglist.user_id == user.id).all()
    )
    subscribed_map = {ml.listname: ml for ml in subscribed_lists}
    subscribed_names = set(subscribed_map.keys())

    lists_to_add = []
    removed = False

    for listname in mailinglists:
        status = mailinglists.get(listname, False)
        if status and listname not in subscribed_names:
            lists_to_add.append(
                Mailinglist(
                    listname=listname,
                    email=loaded_user.email,
                    user_id=user.id,
                    user=loaded_user,
                )
            )
        elif not status and listname in subscribed_names:
            removed = True
            db.delete(subscribed_map[listname])

    if lists_to_add:
        db.add_all(lists_to_add)
    if lists_to_add or removed:
        db.flush()
    return {}
