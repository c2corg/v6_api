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

from c2corg_api.models.document import DocumentGeometry
from c2corg_api.models.route import Route

from c2corg_api.models import DBSession, Base
from c2corg_api.search import configure_es_from_config, get_queue_config

from pyramid.settings import asbool

log = logging.getLogger(__name__)
load_dotenv()


class RootFactory(ACLDefault):
    __name__ = "RootFactory"


def main(global_config, **settings):
    """This function returns a Pyramid WSGI application."""

    # Configure SQLAlchemy
    engine = engine_from_config(settings, "sqlalchemy.")
    DBSession.configure(bind=engine)
    Base.metadata.bind = engine

    # Configure ElasticSearch
    configure_es_from_config(settings)

    config = Configurator(settings=settings)
    config.include("cornice")
    config.registry.queue_config = get_queue_config(settings)

    # FIXME? Make sure this tween is run after the JWT validation
    # Using an explicit ordering in config files might be needed.
    config.add_tween(
        "c2corg_api.tweens.rate_limiting." + "rate_limiting_tween_factory",
        under="pyramid_tm.tm_tween_factory",
    )

    bypass_auth = False
    if "noauthorization" in settings:
        bypass_auth = asbool(settings["noauthorization"])

    if not bypass_auth:
        config.include("pyramid_jwtauth")
        # Intercept request handling to validate token against the database
        config.add_tween(
            "c2corg_api.tweens.jwt_database_validation."
            + "jwt_database_validation_tween_factory"
        )
        # Inject ACLs
        config.set_root_factory(RootFactory)
    else:
        log.warning("Bypassing authorization")

    configure_caches(settings)
    configure_feed(settings, config)
    configure_anonymous(settings, config)

    # Scan MUST be the last call otherwise ACLs will not be set
    # and the permissions would be bypassed
    config.scan(ignore="c2corg_api.tests")
    return config.make_wsgi_app()


# validate db connection before using it
@event.listens_for(Pool, "checkout")
def ping_connection(dbapi_connection, connection_record, connection_proxy):
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("SELECT 1")
    except Exception:
        # raise DisconnectionError - pool will try
        # connecting again up to three times before raising.
        raise exc.DisconnectionError()
    cursor.close()


def configure_feed(settings, config):
    account_id = None

    if settings.get("feed.admin_user_account"):
        account_id = int(settings.get("feed.admin_user_account"))
    config.registry.feed_admin_user_account_id = account_id


def configure_anonymous(settings, config):
    account_id = None

    if settings.get("guidebook.anonymous_user_account"):
        account_id = int(settings.get("guidebook.anonymous_user_account"))
    config.registry.anonymous_user_id = account_id


@event.listens_for(DocumentGeometry, "after_insert")
def process_new_waypoint(mapper, connection, geometry):
    """Processes a new waypoint to find its public transports after
    inserting it into documents_geometries."""
    waypoint_id = geometry.document_id

    max_distance_waypoint_to_stoparea = int(
        os.environ.get("MAX_DISTANCE_WAYPOINT_TO_STOPAREA")
    )
    walking_speed = float(os.environ.get("WALKING_SPEED"))
    max_stop_area = int(os.environ.get("MAX_STOP_AREA_FOR_1_WAYPOINT"))
    api_key = os.environ.get("NAVITIA_API_KEY")
    max_duration = int(max_distance_waypoint_to_stoparea / walking_speed)

    # Check if document is a waypoint
    document_type = connection.execute(
        text(
            """
        SELECT type FROM guidebook.documents
        WHERE document_id = :waypoint_id
    """
        ),
        {"waypoint_id": waypoint_id},
    ).scalar()

    if document_type != "w":
        return

    waypoint_type = connection.execute(
        text(
            """
        SELECT waypoint_type FROM guidebook.waypoints
        WHERE document_id = :waypoint_id
    """
        ),
        {"waypoint_id": waypoint_id},
    ).scalar()

    if waypoint_type != "access":
        return

    log.warning(f"Waypoint Navitia processing with ID: {waypoint_id}")

    # Get waypoint coordinates
    lon_lat = connection.execute(
        text(
            """
        SELECT ST_X(ST_Transform(geom, 4326)) || ',' || ST_Y(ST_Transform(geom, 4326))
        FROM guidebook.documents_geometries
        WHERE document_id = :waypoint_id
    """  # noqa: E501
        ),
        {"waypoint_id": waypoint_id},
    ).scalar()

    if not lon_lat:
        log.warning(f"Coordinates not found for waypoint {waypoint_id}")
        return

    lon, lat = lon_lat.strip().split(",")

    # Navitia request
    places_url = f"https://api.navitia.io/v1/coord/{lon};{lat}/places_nearby"
    places_params = {
        "type[]": "stop_area",
        "count": max_stop_area,
        "distance": max_distance_waypoint_to_stoparea,
    }
    navitia_headers = {"Authorization": api_key}

    places_response = requests.get(
        places_url, headers=navitia_headers, params=places_params
    )
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
            "max_walking_duration_to_pt": max_duration,
            "direct_path_mode[]": "walking",
            "from": stop_id,
            "direct_path": "only_with_alternatives",
        }

        journey_response = requests.get(
            journey_url, headers=navitia_headers, params=journey_params
        )
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
        existing_stop_query = text(
            """
            SELECT stoparea_id FROM guidebook.stopareas
            WHERE navitia_id = :stop_id LIMIT 1
        """
        )
        existing_stop_id = connection.execute(
            existing_stop_query, {"stop_id": stop_id}
        ).scalar()

        if not existing_stop_id:
            # Get stop informations
            stop_info_url = f"https://api.navitia.io/v1/places/{stop_id}"
            stop_info_response = requests.get(
                stop_info_url, headers=navitia_headers
            )
            stop_info = stop_info_response.json()

            if "places" not in stop_info or not stop_info["places"]:
                continue

            for line in stop_info["places"][0]["stop_area"].get("lines", []):
                line_full_name = line.get("name", "")
                line_name = line.get("code", "")
                operator_name = line.get("network", {}).get("name", "")
                mode = line.get("commercial_mode", {}).get("name", "")

                # Create a new stop and its relation with waypoint
                insert_stoparea_query = text(
                    """
                    WITH new_stoparea AS (
                        INSERT INTO guidebook.stopareas
                        (navitia_id, stoparea_name, line, operator, geom) VALUES (:stop_id, :stop_name, :line, :operator, ST_Transform(ST_SetSRID(ST_MakePoint(:lon_stop, :lat_stop), 4326), 3857))
                        RETURNING stoparea_id
                    )
                    INSERT INTO guidebook.waypoints_stopareas
                    (stoparea_id, waypoint_id, distance)
                    SELECT stoparea_id, :waypoint_id, :distance_km
                    FROM new_stoparea
                """  # noqa: E501
                )

                connection.execute(
                    insert_stoparea_query,
                    {
                        "stop_id": stop_id,
                        "stop_name": stop_name,
                        "line": f"{mode} {line_name} - {line_full_name}",
                        "operator": operator_name,
                        "lon_stop": lon_stop,
                        "lat_stop": lat_stop,
                        "waypoint_id": waypoint_id,
                        "distance_km": distance_km,
                    },
                )
        else:
            # If stop already exists, only add relation
            insert_relation_query = text(
                """
                INSERT INTO guidebook.waypoints_stopareas
                (stoparea_id, waypoint_id, distance)
                VALUES (:stoparea_id, :waypoint_id, :distance_km)
            """
            )

            connection.execute(
                insert_relation_query,
                {
                    "stoparea_id": existing_stop_id,
                    "waypoint_id": waypoint_id,
                    "distance_km": distance_km,
                },
            )

    log.warning(f"Traitement terminé pour le waypoint {waypoint_id}")

# pylint: disable=too-complex,too-many-branches,too-many-statements


@event.listens_for(Route, "after_insert")
@event.listens_for(Route, "after_update")
# pylint: disable=too-complex,too-many-branches,too-many-statements
def calculate_route_duration(mapper, connection, route):
    """
    Calcule la durée estimée d'un itinéraire
    après son insertion ou sa mise à jour,
    en intégrant les règles métier mises à
    jour du script bash.
    """
    route_id = route.document_id

    log.warn(f"Calculating duration for route ID: {route_id}")

    # Récupération des activités
    activities = route.activities if route.activities is not None else []

    # Définition des activités considérées comme "grimpantes" ou techniques
    climbing_activities = [
        "rock_climbing",
        "ice_climbing",
        "mountain_climbing",
        "snow_ice_mixed",
        "via_ferrata",
        "paragliding",
        "slacklining",
    ]
    is_climbing = any(
        activity in climbing_activities for activity in activities
    )

    # Définition des bornes de cohérence de durée (en heures)
    min_duration_hours = 0.5  # 30 minutes
    max_duration_hours = 18.0  # 18 heures

    # MODIFICATION 1: Égaliser les dénivelés si l'un est NULL et l'autre non
    height_diff_up = route.height_diff_up
    height_diff_down = route.height_diff_down
    if height_diff_up is None and height_diff_down is not None:
        height_diff_up = height_diff_down
    elif height_diff_down is None and height_diff_up is not None:
        height_diff_down = height_diff_up

    # MODIFICATION 2: Pour la grimpe, permettre le calcul avec seulement
    # difficulties_height
    if (
        is_climbing
        and getattr(route, "height_diff_difficulties", None) is not None
    ):
        if (
            route.route_length is None or height_diff_up is None
        ) and route.height_diff_difficulties > 0:
            # Cas spécial : calcul uniquement avec difficulties_height
            v_diff = 50.0  # Vitesse ascensionnelle pour les difficultés (m/h)
            dm = float(route.height_diff_difficulties) / v_diff

            # Validation des bornes de cohérence
            if dm < min_duration_hours or dm > max_duration_hours:
                log.warn(
                    f"Route {route_id}: Calculated duration ({dm:.2f} hours) is out of bounds - setting to NULL")  # noqa: E501
                calculated_duration_in_days = None
            else:
                calculated_duration_in_days = dm / 24.0

            # Mise à jour de la durée calculée dans la base de données
            connection.execute(
                text(
                    """
                UPDATE guidebook.routes
                SET calculated_duration = :duration
                WHERE document_id = :route_id
            """
                ),
                {
                    "duration": calculated_duration_in_days,
                    "route_id": route_id,
                },
            )
            log.warn(
                f"Route {route_id}: Database updated with calculated_duration = {calculated_duration_in_days} days (based on difficulties_height only)."  # noqa: E501
            )
            return

    # Convertir les valeurs de base (avec COALESCE pour remplacer NULL par 0)
    h = (
        float(route.route_length if route.route_length is not None else 0)
        / 1000
    )  # km
    # m (dénivelé positif total)
    dp = float(height_diff_up if height_diff_up is not None else 0)
    dn = float(height_diff_down if height_diff_down is not None else 0)  # m

    # Initialiser la durée minimale
    min_duration = None

    # MODIFICATION 3: Calculer la durée pour chaque activité et garder la plus
    # courte
    for activity in activities:
        dm = None

        # CALCUL POUR LES ITINÉRAIRES DE GRIMPE
        if activity in climbing_activities:
            v_diff = 50.0  # Vitesse ascensionnelle pour les difficultés (m/h)

            # Récupération du dénivelé des difficultés (si l'attribut existe)
            diff_height = getattr(route, "height_diff_difficulties", None)

            if diff_height is not None and diff_height > 0:
                d_diff = float(diff_height)  # Dénivelé des difficultés

                # Vérifier la cohérence: le dénivelé des difficultés ne peut
                # pas être supérieur au dénivelé total positif
                if dp > 0 and d_diff > dp:
                    log.warn(
                        f"Route {route_id}: Inconsistent difficulties_height ({d_diff}m) > height_diff_up ({dp}m). Skipping for this activity."  # noqa: E501
                    )
                    continue  # Passer à l'activité suivante

                # Dénivelé de l'approche (au moins 0)
                d_app = max(dp - d_diff, 0)

                # Temps pour parcourir les difficultés (en heures)
                t_diff = d_diff / v_diff

                # Calcul du temps d'approche (même formule que randonnée)
                if d_app > 0:
                    # Paramètres par défaut pour l'approche (comme randonnée)
                    v = 5.0  # km/h (vitesse horizontale)
                    a = 300.0  # m/h (montée)
                    d = 500.0  # m/h (descente)

                    dh = h / v  # durée basée sur la distance horizontale
                    # durée basée sur le dénivelé d'approche et la descente
                    dv = (d_app / a) + (dn / d)

                    # Temps d'approche
                    if dh < dv:
                        t_app = dv + (dh / 2)
                    else:
                        t_app = (dv / 2) + dh
                else:
                    t_app = 0

                # Temps total selon la formule : T = max(Tdiff, Tapp) + 0.5 *
                # min(Tdiff, Tapp)
                dm = max(t_diff, t_app) + 0.5 * min(t_diff, t_app)

            else:
                # Si dénivelé des difficultés non disponible ou nul, on utilise
                # le dénivelé total
                dm = dp / v_diff

            log.warn(
                f"Calculated climbing route duration for route {route_id} (activity {activity}): {dm:.2f} hours"  # noqa: E501
            )

        # CALCUL POUR LES AUTRES ITINÉRAIRES (NON GRIMPANTS)
        else:
            # Définir les paramètres selon l'activité
            if activity == "hiking":
                v = 5.0  # km/h (vitesse horizontale)
                a = 300.0  # m/h (montée)
                d = 500.0  # m/h (descente)
            elif activity == "snowshoeing":
                v = 4.5
                a = 250.0
                d = 400.0
            elif activity == "skitouring":
                v = 5.0
                a = 300.0
                d = 1500.0
            elif activity == "mountain_biking":
                v = 15.0
                a = 250.0
                d = 1000.0
            else:
                # Valeurs par défaut (comme randonnée)
                v = 5.0
                a = 300.0
                d = 500.0

            # Calcul de la durée
            dh = h / v  # durée basée sur la distance horizontale
            dv = (dp / a) + (dn / d)  # durée basée sur les dénivelés

            # Calcul de la durée finale en heures
            if dh < dv:
                dm = dv + (dh / 2)
            else:
                dm = (dv / 2) + dh

            log.warn(
                f"Calculated standard route duration for route {route_id} (activity {activity}): {dm:.2f} hours"  # noqa: E501
            )

        # Garder la durée la plus courte parmi toutes les activités
        if dm is not None and (min_duration is None or dm < min_duration):
            min_duration = dm

    # Validation des bornes de cohérence
    if (
        min_duration is None
        or min_duration < min_duration_hours
        or min_duration > max_duration_hours
    ):
        log.warn(
            f"Route {route_id}: Calculated duration ({min_duration:.2f} hours) is out of bounds (min={min_duration_hours}h, max={max_duration_hours}h) or NULL. Setting duration to NULL."  # noqa: E501
        )
        calculated_duration_in_days = None
    else:
        # Conversion de la durée finale d'heures en jours pour la base de
        # données
        calculated_duration_in_days = min_duration / 24.0

    # Mise à jour de la durée calculée dans la base de données
    connection.execute(
        text(
            """
        UPDATE guidebook.routes
        SET calculated_duration = :duration
        WHERE document_id = :route_id
    """
        ),
        {"duration": calculated_duration_in_days, "route_id": route_id},
    )
    log.warn(
        f"Route {route_id}: Database updated with calculated_duration = {calculated_duration_in_days} days."  # noqa: E501
    )
