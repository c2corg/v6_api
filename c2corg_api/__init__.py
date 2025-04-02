import logging
import os
import requests

from c2corg_api.caching import configure_caches
from pyramid.config import Configurator
from sqlalchemy import engine_from_config, exc, event
from sqlalchemy.pool import Pool
from sqlalchemy import text
from dotenv import load_dotenv

from c2corg_api.models.document import DocumentGeometry;

from c2corg_api.models import DBSession, Base
from c2corg_api.search import configure_es_from_config, get_queue_config

from pyramid.security import Allow, Everyone, Authenticated

from pyramid.settings import asbool

log = logging.getLogger(__name__)
load_dotenv()


class RootFactory(object):
    __name__ = 'RootFactory'
    __acl__ = [
            (Allow, Everyone, 'public'),
            (Allow, Authenticated, 'authenticated'),
            (Allow, 'group:moderators', 'moderator')
    ]

    def __init__(self, request):
        pass


def main(global_config, **settings):
    """ This function returns a Pyramid WSGI application.
    """

    # Configure SQLAlchemy
    engine = engine_from_config(settings, 'sqlalchemy.')
    DBSession.configure(bind=engine)
    Base.metadata.bind = engine

    # Configure ElasticSearch
    configure_es_from_config(settings)

    config = Configurator(settings=settings)
    config.include('cornice')
    config.registry.queue_config = get_queue_config(settings)

    # FIXME? Make sure this tween is run after the JWT validation
    # Using an explicit ordering in config files might be needed.
    config.add_tween('c2corg_api.tweens.rate_limiting.' +
                     'rate_limiting_tween_factory',
                     under='pyramid_tm.tm_tween_factory')

    bypass_auth = False
    if 'noauthorization' in settings:
        bypass_auth = asbool(settings['noauthorization'])

    if not bypass_auth:
        config.include("pyramid_jwtauth")
        # Intercept request handling to validate token against the database
        config.add_tween('c2corg_api.tweens.jwt_database_validation.' +
                         'jwt_database_validation_tween_factory')
        # Inject ACLs
        config.set_root_factory(RootFactory)
    else:
        log.warning('Bypassing authorization')

    configure_caches(settings)
    configure_feed(settings, config)
    configure_anonymous(settings, config)

    # Scan MUST be the last call otherwise ACLs will not be set
    # and the permissions would be bypassed
    config.scan(ignore='c2corg_api.tests')
    return config.make_wsgi_app()


# validate db connection before using it
@event.listens_for(Pool, 'checkout')
def ping_connection(dbapi_connection, connection_record, connection_proxy):
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute('SELECT 1')
    except Exception:
        # raise DisconnectionError - pool will try
        # connecting again up to three times before raising.
        raise exc.DisconnectionError()
    cursor.close()


def configure_feed(settings, config):
    account_id = None

    if settings.get('feed.admin_user_account'):
        account_id = int(settings.get('feed.admin_user_account'))
    config.registry.feed_admin_user_account_id = account_id


def configure_anonymous(settings, config):
    account_id = None

    if settings.get('guidebook.anonymous_user_account'):
        account_id = int(settings.get('guidebook.anonymous_user_account'))
    config.registry.anonymous_user_id = account_id

@event.listens_for(DocumentGeometry, 'after_insert')
def process_new_waypoint(mapper, connection, geometry):
    """Processes a new waypoint to find its public transports after inserting it into documents_geometries."""
    waypoint_id = geometry.document_id

    max_distance_waypoint_to_stoparea = int(os.environ.get("MAX_DISTANCE_WAYPOINT_TO_STOPAREA"))
    walking_speed = float(os.environ.get("WALKING_SPEED"))
    max_stop_area = int(os.environ.get("MAX_STOP_AREA_FOR_1_WAYPOINT"))
    api_key = os.environ.get("NAVITIA_API_KEY")
    max_duration = int(max_distance_waypoint_to_stoparea / walking_speed)
    
    # Check if document is a waypoint
    document_type = connection.execute(text("""
        SELECT type FROM guidebook.documents 
        WHERE document_id = :waypoint_id
    """), {"waypoint_id": waypoint_id}).scalar()
    
    if document_type != 'w':  
        return
    
    waypoint_type = connection.execute(text("""
        SELECT waypoint_type FROM guidebook.waypoints
        WHERE document_id = :waypoint_id
    """), {"waypoint_id": waypoint_id}).scalar()
    
    if waypoint_type != 'access':  
        return
    
    log.warning(f"Waypoint Navitia processing with ID: {waypoint_id}")
    
    # Get waypoint coordinates
    lon_lat = connection.execute(text("""
        SELECT ST_X(ST_Transform(geom, 4326)) || ',' || ST_Y(ST_Transform(geom, 4326)) 
        FROM guidebook.documents_geometries 
        WHERE document_id = :waypoint_id
    """), {"waypoint_id": waypoint_id}).scalar()
    
    if not lon_lat:
        log.warning(f"Coordinates not found for waypoint {waypoint_id}")
        return
    
    lon, lat = lon_lat.strip().split(',')
    
    # Navitia request
    places_url = f"https://api.navitia.io/v1/coord/{lon};{lat}/places_nearby"
    places_params = {
        "type[]": "stop_area",
        "count": max_stop_area,
        "distance": max_distance_waypoint_to_stoparea
    }
    navitia_headers = {"Authorization": api_key}
    
    places_response = requests.get(places_url, headers=navitia_headers, params=places_params)
    places_data = places_response.json()
    
    if "places_nearby" not in places_data or not places_data["places_nearby"]:
        log.warning(f"No Navitia stops found for the waypoint {waypoint_id}")
        return
    
    # For each result
    for place in places_data["places_nearby"]:
        if place.get("embedded_type") != "stop_area":
            continue
            
        stop_id = place["id"]
        stop_name = place["name"]
        lat_stop = place["stop_area"]["coord"]["lat"]
        lon_stop = place["stop_area"]["coord"]["lon"]
        
        # Get the travel time by walking
        journey_url = "https://api.navitia.io/v1/journeys"
        journey_params = {
            "to": f"{lon};{lat}",
            "walking_speed": walking_speed,
            "max_walking_direct_path_duration": max_duration,
            "direct_path_mode[]": "walking",
            "from": stop_id,
            "direct_path": "only_with_alternatives"
        }
        
        journey_response = requests.get(journey_url, headers=navitia_headers, params=journey_params)
        journey_data = journey_response.json()
        
        if "error" in journey_data:
            continue
            
        # Get the walk duration
        if "journeys" not in journey_data or not journey_data["journeys"]:
            continue
            
        duration = journey_data["journeys"][0].get("duration", 0)
        
        # Convert to distance
        distance_km = (duration * walking_speed) / 1000
        
        # Check if stop already exists
        existing_stop_query = text("""
            SELECT stoparea_id FROM guidebook.stopareas 
            WHERE navitia_id = :stop_id LIMIT 1
        """)
        existing_stop_id = connection.execute(existing_stop_query, {"stop_id": stop_id}).scalar()
        
        if not existing_stop_id:
            # Get stop informations
            stop_info_url = f"https://api.navitia.io/v1/places/{stop_id}"
            stop_info_response = requests.get(stop_info_url, headers=navitia_headers)
            stop_info = stop_info_response.json()
            
            if "places" not in stop_info or not stop_info["places"]:
                continue
                
            for line in stop_info["places"][0]["stop_area"].get("lines", []):
                line_full_name = line.get("name", "")
                line_name = line.get("code", "")
                operator_name = line.get("network", {}).get("name", "")
                mode = line.get("commercial_mode", {}).get("name", "")
                
                # Create a new stop and its relation with waypoint
                insert_stoparea_query = text("""
                    WITH new_stoparea AS (
                        INSERT INTO guidebook.stopareas 
                        (navitia_id, stoparea_name, line, operator, geom) 
                        VALUES (:stop_id, :stop_name, :line, :operator, ST_Transform(ST_SetSRID(ST_MakePoint(:lon_stop, :lat_stop), 4326), 3857))
                        RETURNING stoparea_id
                    )
                    INSERT INTO guidebook.waypoints_stopareas 
                    (stoparea_id, waypoint_id, distance) 
                    SELECT stoparea_id, :waypoint_id, :distance_km
                    FROM new_stoparea
                """)
                
                connection.execute(insert_stoparea_query, {
                    "stop_id": stop_id,
                    "stop_name": stop_name,
                    "line": f"{mode} {line_name} - {line_full_name}",
                    "operator": operator_name,
                    "lon_stop": lon_stop,
                    "lat_stop": lat_stop,
                    "waypoint_id": waypoint_id,
                    "distance_km": distance_km
                })
        else:
            # If stop already exists, only add relation
            insert_relation_query = text("""
                INSERT INTO guidebook.waypoints_stopareas 
                (stoparea_id, waypoint_id, distance) 
                VALUES (:stoparea_id, :waypoint_id, :distance_km)
            """)
            
            connection.execute(insert_relation_query, {
                "stoparea_id": existing_stop_id,
                "waypoint_id": waypoint_id,
                "distance_km": distance_km
            })
    
    log.warning(f"Traitement terminé pour le waypoint {waypoint_id}")

