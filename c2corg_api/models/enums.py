from sqlalchemy import Enum

from c2corg_api.models import Base, schema
from c2corg_api.models.common import attributes


def enum(name, types):
    return Enum(
        name=name, metadata=Base.metadata, schema=schema, *types)


quality_type = enum(
    'quality_type', attributes.quality_types)
waypoint_type = enum(
    'waypoint_type', attributes.waypoint_types)
activity_type = enum(
    'activity_type', attributes.activities)
climbing_outdoor_type = enum(
    'climbing_outdoor_type', attributes.climbing_outdoor_types)
climbing_indoor_type = enum(
    'climbing_indoor_type', attributes.climbing_indoor_types)
public_transportation_type = enum(
    'public_transportation_type', attributes.public_transportation_types)
product_type = enum(
    'product_type', attributes.product_types)
ground_type = enum(
    'ground_type', attributes.ground_types)
weather_station_type = enum(
    'weather_station_type', attributes.weather_station_types)
rain_proof_type = enum(
    'rain_proof_type', attributes.rain_proof_types)
public_transportation_rating = enum(
    'public_transportation_rating', attributes.public_transportation_ratings)
paragliding_rating = enum(
    'paragliding_rating', attributes.paragliding_ratings)
children_proof_type = enum(
    'children_proof_type', attributes.children_proof_types)
snow_clearance_rating = enum(
    'snow_clearance_rating', attributes.snow_clearance_ratings)
exposition_rating = enum(
    'exposition_rating', attributes.exposition_ratings)
rock_type = enum(
    'rock_type', attributes.rock_types)
orientation_type = enum(
    'orientation_type', attributes.orientation_types)
month_type = enum(
    'month_type', attributes.months)
parking_fee_type = enum(
    'parking_fee_type', attributes.parking_fee_types)
climbing_style = enum(
    'climbing_style', attributes.climbing_styles)
access_time_type = enum(
    'access_time_type', attributes.access_times)
climbing_rating = enum(
    'climbing_rating', attributes.climbing_ratings)
bouldering_rating = enum(
    'bouldering_rating', attributes.bouldering_rating)
equipment_rating = enum(
    'equipment_rating', attributes.equipment_ratings)
route_type = enum(
    'route_type', attributes.route_types)
route_duration_type = enum(
    'route_duration_type', attributes.route_duration_types)
glacier_gear_type = enum(
    'glacier_gear_type', attributes.glacier_gear_types)
route_configuration_type = enum(
    'route_configuration_type', attributes.route_configuration_types)
ski_rating = enum(
    'ski_rating', attributes.ski_ratings)
labande_ski_rating = enum(
    'labande_ski_rating', attributes.labande_ski_ratings)
global_rating = enum(
    'global_rating', attributes.global_ratings)
engagement_rating = enum(
    'engagement_rating', attributes.engagement_ratings)
risk_rating = enum(
    'risk_rating', attributes.risk_ratings)
ice_rating = enum(
    'ice_rating', attributes.ice_ratings)
mixed_rating = enum(
    'mixed_rating', attributes.mixed_ratings)
exposition_rock_rating = enum(
    'exposition_rock_rating', attributes.exposition_rock_ratings)
aid_rating = enum(
    'aid_rating', attributes.aid_ratings)
via_ferrata_rating = enum(
    'via_ferrata_rating', attributes.via_ferrata_ratings)
hiking_rating = enum(
    'hiking_rating', attributes.hiking_ratings)
snowshoe_rating = enum(
    'snowshoe_rating', attributes.snowshoe_ratings)
mtb_up_rating = enum(
    'mtb_up_rating', attributes.mtb_up_ratings)
mtb_down_rating = enum(
    'mtb_down_rating', attributes.mtb_down_ratings)
map_editor = enum(
    'map_editor', attributes.map_editors)
map_scale = enum(
    'map_scale', attributes.map_scales)
area_type = enum(
    'area_type', attributes.area_types)
user_category = enum(
    'user_category', attributes.user_categories)
frequentation_type = enum(
    'frequentation_type', attributes.frequentation_types)
access_condition = enum(
    'access_condition', attributes.access_conditions)
lift_status = enum(
    'lift_status', attributes.lift_status)
condition_rating = enum(
    'condition_rating', attributes.condition_ratings)
glacier_rating = enum(
    'glacier_rating', attributes.glacier_ratings)
avalanche_signs = enum(
    'avalanche_signs', attributes.avalanche_signs)
hut_status = enum(
    'hut_status', attributes.hut_status)
image_category = enum(
    'image_category', attributes.image_categories)
image_type = enum(
    'image_type', attributes.image_types)
custodianship_type = enum(
    'custodianship_type', attributes.custodianship_types)
article_category = enum(
    'article_category', attributes.article_categories)
article_type = enum(
    'article_type', attributes.article_types)
book_type = enum(
    'book_type', attributes.book_types)
feed_change_type = enum(
    'feed_change_type', attributes.feed_change_types)
event_type = enum(
    'event_type', attributes.event_types)
event_activity = enum(
    'event_activity', attributes.event_activities)
author_status = enum(
    'author_status', attributes.author_statuses)
activity_rate = enum(
    'activity_rate', attributes.activity_rates)
supervision = enum(
    'supervision', attributes.supervision)
qualification = enum(
    'qualification', attributes.qualification)
gender = enum(
    'gender', attributes.genders)
previous_injuries = enum(
    'previous_injuries', attributes.previous_injuries)
severity = enum(
    'severity', attributes.severities)
autonomy = enum(
    'autonomy', attributes.autonomies)
avalanche_level = enum(
    'avalanche_level', attributes.avalanche_levels)
avalanche_slope = enum(
    'avalanche_slope', attributes.avalanche_slopes)
slackline_type = enum(
    'slackline_type', attributes.slackline_types)
lang = enum(
    'lang', attributes.default_langs)
snow_quality_ratings = enum(
    'snow_quality_ratings', attributes.snow_quality_ratings)
snow_quantity_ratings = enum(
    'snow_quantity_ratings', attributes.snow_quantity_ratings)
