from c2corg_api import DBSession
from c2corg_api.models.area import schema_listing_area, Area
from c2corg_api.models.schema_utils import SchemaAssociationDoc
from c2corg_api.models.user import User
from c2corg_api.views import cors_policy, restricted_json_view, \
    restricted_view, to_json_dict, set_best_locale
from c2corg_api.views.validation import validate_preferred_lang_param
from c2corg_common.attributes import activities, default_langs
from cornice.resource import resource
from cornice.validators import colander_body_validator
from colander import MappingSchema, SchemaNode, String, Boolean, Sequence, \
    OneOf, required
from sqlalchemy.orm import joinedload, load_only


class FilterPreferencesSchema(MappingSchema):
    lang_preferences = SchemaNode(
        Sequence(), SchemaNode(String(), validator=OneOf(default_langs)),
        missing=required)
    activities = SchemaNode(
        Sequence(),
        SchemaNode(String(), validator=OneOf(activities)),
        missing=required)
    areas = SchemaNode(
        Sequence(), SchemaAssociationDoc(), missing=required)
    followed_only = SchemaNode(Boolean(), missing=required)


@resource(path='/users/preferences', cors_policy=cors_policy)
class UserFilterPreferencesRest(object):

    def __init__(self, request):
        self.request = request

    def get_user(self, with_area_locales=True):
        user_id = self.request.authenticated_userid

        area_joinedload = \
            joinedload(User.feed_filter_areas). \
            load_only(
                Area.document_id, Area.area_type, Area.version,
                Area.protected, Area.type)

        if with_area_locales:
            area_joinedload = area_joinedload. \
                joinedload('locales'). \
                load_only('lang', 'title', 'version')

        return DBSession. \
            query(User). \
            options(area_joinedload). \
            get(user_id)

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
            'lang_preferences': user.feed_filter_lang_preferences,
            'followed_only': user.feed_followed_only,
            'activities': user.feed_filter_activities,
            'areas': [
                to_json_dict(a, schema_listing_area) for a in areas
            ]
        }

    @restricted_json_view(
        schema=FilterPreferencesSchema(), validators=[colander_body_validator])
    def post(self):
        user = self.get_user(with_area_locales=False)

        validated = self.request.validated
        user.feed_filter_lang_preferences = validated['lang_preferences']
        user.feed_followed_only = validated['followed_only']
        user.feed_filter_activities = validated['activities']

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
