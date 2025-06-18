import logging
import os
import requests

from c2corg_api.caching import configure_caches
from c2corg_api.security.acl import ACLDefault
from pyramid.config import Configurator
from sqlalchemy import engine_from_config, exc, event
from sqlalchemy.pool import Pool
from sqlalchemy import text
from dotenv import load_dotenv

from c2corg_api.models.document import DocumentGeometry;
from c2corg_api.models.route import Route

from c2corg_api.models import DBSession, Base
from c2corg_api.search import configure_es_from_config, get_queue_config

from pyramid.settings import asbool

log = logging.getLogger(__name__)
load_dotenv()


class RootFactory(ACLDefault):
    __name__ = 'RootFactory'


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

@event.listens_for(Route, 'after_insert')
@event.listens_for(Route, 'after_update')
def calculate_route_duration(mapper, connection, route):
    """Calcule la durée estimée d'un itinéraire après son insertion ou sa mise à jour."""
    route_id = route.document_id
    
    log.warn(f"Calculating duration for route ID: {route_id}")
    
    # Récupération des activités
    activities = route.activities
    is_climbing = any(activity in ['rock_climbing', 'ice_climbing', 'mountain_climbing'] for activity in activities)
    
    # Si length, height_diff_up ou height_diff_down sont NULL ou si length = 0, pas de calcul
    if route.route_length is None or route.route_length == 0 or \
       route.height_diff_up is None or route.height_diff_down is None:
        log.warn(f"Route {route_id} has null or zero values - no duration calculation")
        connection.execute(text("""
            UPDATE guidebook.routes
            SET calculated_duration = NULL
            WHERE document_id = :route_id
        """), {"route_id": route_id})
        return
    
    # Convertir les valeurs de base
    h = float(route.route_length) / 1000  # km
    dp = float(route.height_diff_up)      # m (dénivelé positif total)
    dn = float(route.height_diff_down)    # m
    
    # CALCUL POUR LES ITINÉRAIRES DE GRIMPE
    if is_climbing:
        # Vitesse ascensionnelle pour les difficultés (m/h)
        v_diff = 50.0
        
        # Récupération du dénivelé des difficultés
        # Note: Il faut s'assurer que cet attribut existe dans votre modèle Route
        diff_height = getattr(route, 'difficulties_height', None)
        
        if diff_height is not None and diff_height > 0:
            # Calcul spécifique pour les itinéraires grimpants avec dénivelé des difficultés
            d_diff = float(diff_height)  # Dénivelé des difficultés
            d_app = dp - d_diff         # Dénivelé de l'approche
            
            # Temps pour parcourir les difficultés (en heures)
            t_diff = d_diff / v_diff
            
            # Calcul du temps d'approche (même formule que randonnée)
            if d_app > 0:
                # Paramètres par défaut pour l'approche (comme randonnée)
                v = 5.0    # km/h (vitesse horizontale)
                a = 300.0  # m/h (montée)
                d = 500.0  # m/h (descente)
                
                dh = h / v                  # durée basée sur la distance horizontale
                dv = (d_app / a) + (dn / d) # durée basée sur le dénivelé d'approche et la descente
                
                # Temps d'approche
                if dh < dv:
                    t_app = dv + (dh / 2)
                else:
                    t_app = (dv / 2) + dh
            else:
                t_app = 0
                
            # Temps total selon la formule : T = max(Tdiff, Tapp) + 0.5 * min(Tdiff, Tapp)
            dm = max(t_diff, t_app) + 0.5 * min(t_diff, t_app)
            
        else:
            # Si dénivelé des difficultés non disponible, on utilise le dénivelé total
            dm = dp / v_diff
            
        log.warn(f"Calculated climbing route duration for route {route_id}: {dm} hours")
        
    # CALCUL POUR LES AUTRES ITINÉRAIRES (NON GRIMPANTS)
    else:
        # Définir les paramètres selon l'activité
        if 'hiking' in activities:
            v = 5.0    # km/h (vitesse horizontale)
            a = 300.0  # m/h (montée)
            d = 500.0  # m/h (descente)
        elif 'snowshoeing' in activities:
            v = 4.5
            a = 250.0
            d = 400.0
        elif 'skitouring' in activities:
            v = 5.0
            a = 300.0
            d = 1500.0
        elif 'mountain_biking' in activities:
            v = 15.0
            a = 250.0
            d = 1000.0
        else:
            # Valeurs par défaut
            v = 5.0
            a = 300.0
            d = 500.0
        
        # Calcul de la durée
        dh = h / v                  # durée basée sur la distance horizontale
        dv = (dp / a) + (dn / d)    # durée basée sur les dénivelés
        
        # Calcul de la durée finale en heures
        if dh < dv:
            dm = dv + (dh / 2)
        else:
            dm = (dv / 2) + dh
        
        log.warn(f"Calculated standard route duration for route {route_id}: {dm} hours")

     # Conversion de la durée finale d'heures en jours
    if dm:
        dm = dm/24 

    # Mise à jour de la durée calculée dans la base de données
    connection.execute(text("""
        UPDATE guidebook.routes
        SET calculated_duration = :duration
        WHERE document_id = :route_id
    """), {"duration": dm, "route_id": route_id})
