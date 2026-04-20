"""
Document-type configurations — pure copy from
``c2corg_api.views.document_schemas``.

No Pyramid / Cornice dependency.  Router code should import from here
instead of from ``c2corg_api.views.document_schemas``.
"""

from functools import lru_cache

from c2corg_api.models.area import AREA_TYPE, Area, schema_listing_area
from c2corg_api.models.article import ARTICLE_TYPE, Article, schema_listing_article
from c2corg_api.models.book import BOOK_TYPE, Book, schema_listing_book
from c2corg_api.models.common import attributes
from c2corg_api.models.common.fields_area import fields_area
from c2corg_api.models.common.fields_article import fields_article
from c2corg_api.models.common.fields_book import fields_book
from c2corg_api.models.common.fields_coverage import fields_coverage
from c2corg_api.models.common.fields_image import fields_image
from c2corg_api.models.common.fields_outing import fields_outing
from c2corg_api.models.common.fields_route import fields_route
from c2corg_api.models.common.fields_topo_map import fields_topo_map
from c2corg_api.models.common.fields_user_profile import fields_user_profile
from c2corg_api.models.common.fields_waypoint import fields_waypoint
from c2corg_api.models.common.fields_xreport import fields_xreport
from c2corg_api.models.coverage import COVERAGE_TYPE, Coverage, schema_listing_coverage
from c2corg_api.models.document import DocumentGeometry, DocumentLocale
from c2corg_api.models.image import IMAGE_TYPE, Image, schema_listing_image
from c2corg_api.models.outing import OUTING_TYPE, Outing, schema_outing
from c2corg_api.models.route import ROUTE_TYPE, Route, RouteLocale, schema_route
from c2corg_api.models.topo_map import MAP_TYPE, TopoMap, schema_listing_topo_map
from c2corg_api.models.user_profile import (
    USERPROFILE_TYPE,
    UserProfile,
    schema_listing_user_profile,
)
from c2corg_api.models.waypoint import (
    WAYPOINT_TYPE,
    Waypoint,
    WaypointLocale,
    schema_waypoint,
)
from c2corg_api.models.xreport import (
    XREPORT_TYPE,
    Xreport,
    XreportLocale,
    schema_listing_xreport,
)
from c2corg_api.routers.helpers.document_helpers import set_author


class GetDocumentsConfig:
    def __init__(
        self,
        document_type,
        clazz,
        schema,
        clazz_locale=None,
        fields=None,
        listing_fields=None,
        adapt_schema=None,
        include_areas=True,
        include_img_count=False,
        set_custom_fields=None,
    ):
        self.document_type = document_type
        self.clazz = clazz
        self.schema = schema
        self.clazz_locale = clazz_locale
        self.adapt_schema = adapt_schema
        self.include_areas = include_areas
        self.include_img_count = include_img_count
        self.set_custom_fields = set_custom_fields

        self._set_load_only_fields(fields, listing_fields)

    def _set_load_only_fields(self, fields, listing_fields):
        if not listing_fields:
            listing_fields = self._collect_listing_fields(fields)

        self.fields_document = set(['version', 'protected'])
        self.fields_geometry = set(['version'])
        self.fields_locales = set(['version', 'lang'])

        for field in listing_fields:
            if field in ['locales', 'geometry']:
                pass
            elif field.startswith('locales.'):
                self.fields_locales.add(field.replace('locales.', ''))
            elif field.startswith('geometry.'):
                self.fields_geometry.add(field.replace('geometry.', ''))
            else:
                self.fields_document.add(field)

    def _collect_listing_fields(self, fields):
        listing_fields = set()

        for _, type_config in fields.items():
            listing_fields = listing_fields.union(type_config['listing'])

        return listing_fields

    def get_load_only_fields(self):
        return [getattr(self.clazz, f) for f in self.fields_document]

    def get_load_only_fields_locales(self):
        locale_clazz = self.clazz_locale or DocumentLocale
        return [getattr(locale_clazz, f) for f in self.fields_locales]

    def get_load_only_fields_geometry(self):
        return [getattr(DocumentGeometry, f) for f in self.fields_geometry]


def make_schema_adaptor(adapt_schema_for_type, type_field, field_list_type):
    def adapt_schema(_base_schema, document):
        return adapt_schema_for_type(getattr(document, type_field), field_list_type)

    return adapt_schema


def get_all_fields(fields, activities, field_list_type):
    fields_list = [
        fields.get(activity).get(field_list_type)
        for activity in activities
        if fields.get(activity)
    ]
    return set(sum(fields_list, []))


# ── areas ────────────────────────────────────────────────────────

area_documents_config = GetDocumentsConfig(
    AREA_TYPE,
    Area,
    schema_listing_area,
    listing_fields=fields_area['listing'],
    include_areas=False,
)

# ── articles ─────────────────────────────────────────────────────

article_documents_config = GetDocumentsConfig(
    ARTICLE_TYPE,
    Article,
    schema_listing_article,
    listing_fields=fields_article['listing'],
    include_areas=False,
)

# ── books ────────────────────────────────────────────────────────

book_documents_config = GetDocumentsConfig(
    BOOK_TYPE,
    Book,
    schema_listing_book,
    listing_fields=fields_book['listing'],
    include_areas=False,
)

# ── images ───────────────────────────────────────────────────────

image_documents_config = GetDocumentsConfig(
    IMAGE_TYPE, Image, schema_listing_image, listing_fields=fields_image['listing']
)

# ── outings ──────────────────────────────────────────────────────


def adapt_outing_schema_for_activities(activities, field_list_type):
    if not activities:
        activities = attributes.Activities

    fields = get_all_fields(fields_outing, activities, field_list_type)
    return schema_outing.restrict(fields)


outing_schema_adaptor = make_schema_adaptor(
    adapt_outing_schema_for_activities, 'activities', 'fields'
)
outing_listing_schema_adaptor = make_schema_adaptor(
    adapt_outing_schema_for_activities, 'activities', 'listing'
)

outing_documents_config = GetDocumentsConfig(
    OUTING_TYPE,
    Outing,
    schema_outing,
    fields=fields_outing,
    adapt_schema=outing_listing_schema_adaptor,
    set_custom_fields=set_author,
    include_img_count=True,
)

# ── xreports ─────────────────────────────────────────────────────

xreport_documents_config = GetDocumentsConfig(
    XREPORT_TYPE,
    Xreport,
    schema_listing_xreport,
    clazz_locale=XreportLocale,
    listing_fields=fields_xreport['listing'],
)

# ── routes ───────────────────────────────────────────────────────


def adapt_route_schema_for_activities(activities, field_list_type):
    if not activities:
        activities = [a for a in attributes.Activities if a != 'paragliding']

    fields = get_all_fields(fields_route, activities, field_list_type)
    return schema_route.restrict(fields)


route_schema_adaptor = make_schema_adaptor(
    adapt_route_schema_for_activities, 'activities', 'fields'
)
route_listing_schema_adaptor = make_schema_adaptor(
    adapt_route_schema_for_activities, 'activities', 'listing'
)

route_documents_config = GetDocumentsConfig(
    ROUTE_TYPE,
    Route,
    schema_route,
    clazz_locale=RouteLocale,
    fields=fields_route,
    adapt_schema=route_listing_schema_adaptor,
)

# ── topo maps ────────────────────────────────────────────────────

topo_map_documents_config = GetDocumentsConfig(
    MAP_TYPE,
    TopoMap,
    schema_listing_topo_map,
    listing_fields=fields_topo_map['listing'],
)

# ── user profiles ────────────────────────────────────────────────

user_profile_documents_config = GetDocumentsConfig(
    USERPROFILE_TYPE,
    UserProfile,
    schema_listing_user_profile,
    listing_fields=fields_user_profile['listing'],
)

# ── waypoints ────────────────────────────────────────────────────


@lru_cache(maxsize=None)
def adapt_waypoint_schema_for_type(waypoint_type, field_list_type):
    fields = fields_waypoint.get(waypoint_type, {}).get(field_list_type, [])
    schema = schema_waypoint.restrict(fields)
    return schema


waypoint_schema_adaptor = make_schema_adaptor(
    adapt_waypoint_schema_for_type, 'waypoint_type', 'fields'
)
waypoint_listing_schema_adaptor = make_schema_adaptor(
    adapt_waypoint_schema_for_type, 'waypoint_type', 'listing'
)

waypoint_documents_config = GetDocumentsConfig(
    WAYPOINT_TYPE,
    Waypoint,
    schema_waypoint,
    clazz_locale=WaypointLocale,
    fields=fields_waypoint,
    adapt_schema=waypoint_listing_schema_adaptor,
)

# ── coverages ────────────────────────────────────────────────────

coverage_documents_config = GetDocumentsConfig(
    COVERAGE_TYPE,
    Coverage,
    schema_listing_coverage,
    listing_fields=fields_coverage['listing'],
)

# ── lookup table ─────────────────────────────────────────────────

document_configs = {
    WAYPOINT_TYPE: waypoint_documents_config,
    ROUTE_TYPE: route_documents_config,
    OUTING_TYPE: outing_documents_config,
    IMAGE_TYPE: image_documents_config,
    AREA_TYPE: area_documents_config,
    BOOK_TYPE: book_documents_config,
    XREPORT_TYPE: xreport_documents_config,
    MAP_TYPE: topo_map_documents_config,
    ARTICLE_TYPE: article_documents_config,
    USERPROFILE_TYPE: user_profile_documents_config,
    COVERAGE_TYPE: coverage_documents_config,
}
