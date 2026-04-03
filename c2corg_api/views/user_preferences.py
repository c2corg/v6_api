from c2corg_api.security.acl import ACLDefault
from c2corg_api import DBSession
from c2corg_api.models.area import schema_listing_area, Area
from c2corg_api.models.document import DocumentLocale
from c2corg_api.models.user import User
from c2corg_api.views import cors_policy, restricted_json_view, \
    restricted_view, to_json_dict, set_best_locale
from c2corg_api.views.validation import validate_preferred_lang_param
from c2corg_api.views.pydantic_validator import make_pydantic_validator
from c2corg_api.models.common.attributes import activities, default_langs
from pydantic import BaseModel, field_validator
from typing import List
from cornice.resource import resource
from sqlalchemy.orm import joinedload, load_only


class AreaRef(BaseModel):
    document_id: int


class FilterPreferencesSchema(BaseModel):
    activities: List[str]
    langs: List[str]
    areas: List[AreaRef]
    followed_only: bool

    @field_validator('activities', mode='before')
    @classmethod
    def validate_activities(cls, v):
        for item in v:
            if item not in activities:
                raise ValueError(
                    '{} is not one of {}'.format(item, activities))
        return v

    @field_validator('langs', mode='before')
    @classmethod
    def validate_langs(cls, v):
        for item in v:
            if item not in default_langs:
                raise ValueError(
                    '{} is not one of {}'.format(item, default_langs))
        return v


@resource(path='/users/preferences', cors_policy=cors_policy)
class UserFilterPreferencesRest(ACLDefault):

    def get_user(self, with_area_locales=True):
        user_id = self.request.authenticated_userid

        area_joinedload = \
            joinedload(User.feed_filter_areas). \
            load_only(
                Area.document_id, Area.area_type, Area.version,
                Area.protected, Area.type)

        if with_area_locales:
            area_joinedload = area_joinedload. \
                joinedload(Area.locales). \
                load_only(
                    DocumentLocale.lang,
                    DocumentLocale.title,
                    DocumentLocale.version)

        return DBSession. \
            query(User). \
            options(area_joinedload). \
            filter(User.id == user_id). \
            first()

    @restricted_view(validators=[validate_preferred_lang_param])
    def get(self):
        """Get the filter preferences of the authenticated user.

        Request:
            `GET` `/users/preferences[?pl=...]`

        Parameters:

            `pl=...` (optional)
            When set only the given locale will be included (if available).
            Otherwise the default locale of the user will be used.
        """
        user = self.get_user()

        lang = self.request.validated.get('lang')
        if not lang:
            lang = user.lang

        areas = user.feed_filter_areas
        if lang is not None:
            set_best_locale(areas, lang)

        return {
            'followed_only': user.feed_followed_only,
            'activities': user.feed_filter_activities,
            'langs': user.feed_filter_langs,
            'areas': [
                to_json_dict(a, schema_listing_area) for a in areas
            ]
        }

    @restricted_json_view(
        validators=[make_pydantic_validator(FilterPreferencesSchema)])
    def post(self):
        user = self.get_user(with_area_locales=False)

        validated = self.request.validated
        user.feed_followed_only = validated['followed_only']
        user.feed_filter_activities = validated['activities']
        user.feed_filter_langs = validated['langs']

        # update filter areas: get all areas given in the request and
        # then set on `user.feed_filter_areas`
        area_ids = [
            a['document_id'] for a in validated['areas']
        ]
        areas = []
        if area_ids:
            areas = DBSession. \
                query(Area). \
                filter(Area.document_id.in_(area_ids)). \
                options(
                    load_only(Area.document_id, Area.version, Area.type)). \
                all()

        user.feed_filter_areas = areas

        return {}
