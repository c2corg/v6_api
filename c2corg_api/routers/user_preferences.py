"""
FastAPI User Preferences router.

Provides ``/v2/users/preferences`` — get and set the feed filter
preferences of the authenticated user.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload, load_only

from c2corg_api.database import get_db
from c2corg_api.models.area import Area
from c2corg_api.models.common.attributes import Activities, DefaultLangs
from c2corg_api.models.document import DocumentLocale
from c2corg_api.models.user import User
from c2corg_api.routers.helpers.document_helpers import set_best_locale
from c2corg_api.schemas.listing import AreaListingSchema
from c2corg_api.security.fastapi_security import get_current_user

log = logging.getLogger(__name__)

router = APIRouter(prefix='/v2', tags=['user-preferences'])


class AreaRef(BaseModel):
    document_id: int


class FilterPreferencesSchema(BaseModel):
    activities: List[Activities]
    langs: List[DefaultLangs]
    areas: List[AreaRef]
    followed_only: bool


def _get_user(user_id: int, db: Session, with_area_locales: bool = True):
    """Load the user with feed_filter_areas eagerly loaded."""
    area_joinedload = joinedload(User.feed_filter_areas).load_only(
        Area.document_id, Area.area_type, Area.version, Area.protected, Area.type
    )

    if with_area_locales:
        area_joinedload = area_joinedload.joinedload(Area.locales).load_only(
            DocumentLocale.lang, DocumentLocale.title, DocumentLocale.version
        )

    return db.query(User).options(area_joinedload).filter(User.id == user_id).first()


@router.get('/users/preferences')
def get_preferences(
    pl: Optional[DefaultLangs] = Query(None, description='Preferred language'),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the filter preferences of the authenticated user.

    Parameters
    ----------
    pl : str, optional
        When set only the given locale will be included (if available).
        Otherwise the default locale of the user will be used.
    """
    loaded_user = _get_user(user.id, db, with_area_locales=True)

    lang = pl
    if not lang:
        lang = loaded_user.lang

    areas = loaded_user.feed_filter_areas
    if lang is not None:
        set_best_locale(areas, lang, db=db)

    return {
        'followed_only': loaded_user.feed_followed_only,
        'activities': loaded_user.feed_filter_activities,
        'langs': loaded_user.feed_filter_langs,
        'areas': [
            AreaListingSchema.model_validate(a).model_dump(exclude_none=True)
            for a in areas
        ],
    }


@router.post('/users/preferences', status_code=200)
def post_preferences(
    body: FilterPreferencesSchema,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Set the filter preferences of the authenticated user."""
    loaded_user = _get_user(user.id, db, with_area_locales=False)

    loaded_user.feed_followed_only = body.followed_only
    loaded_user.feed_filter_activities = [a.value for a in body.activities]
    loaded_user.feed_filter_langs = [lang.value for lang in body.langs]

    # update filter areas: get all areas given in the request and
    # then set on `user.feed_filter_areas`
    area_ids = [a.document_id for a in body.areas]
    areas = []
    if area_ids:
        areas = (
            db.query(Area)
            .filter(Area.document_id.in_(area_ids))
            .options(load_only(Area.document_id, Area.version, Area.type))
            .all()
        )

    loaded_user.feed_filter_areas = areas

    return {}
