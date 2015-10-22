from sqlalchemy import Enum

from c2corg_api.models import Base, schema
from c2corg_api import attributes


def enum(name, types):
    return Enum(
        name=name, metadata=Base.metadata, schema=schema, *types)

activity_type = enum(
    'activity_type', attributes.activities)
waypoint_type = enum(
    'waypoint_type', attributes.waypoint_types)
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
custodianship_type = enum(
    'custodianship_type', attributes.custodianship_types)
parking_fee_type = enum(
    'parking_fee_type', attributes.parking_fee_types)
climbing_style = enum(
    'climbing_style', attributes.climbing_styles)
access_time_type = enum(
    'access_time_type', attributes.access_times)
climbing_rating = enum(
    'climbing_rating', attributes.climbing_ratings)
equipment_rating = enum(
    'equipment_rating', attributes.equipment_ratings)
