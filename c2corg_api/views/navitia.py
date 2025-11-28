import json
import logging
import os
import requests
from c2corg_api.models import DBSession
from c2corg_api.models.area import Area, schema_area
from c2corg_api.models.coverage import Coverage
from c2corg_api.models.utils import wkb_to_shape
from c2corg_api.models.waypoint import Waypoint, schema_waypoint
from c2corg_api.views.coverage import get_coverage
from c2corg_api.views.document import LIMIT_DEFAULT
from c2corg_api.views.waypoint import build_reachable_waypoints_query
from c2corg_api.views.route import build_reachable_route_query, build_reachable_route_query_with_waypoints
from shapely import wkb
from shapely.geometry import Point
from pyramid.httpexceptions import HTTPBadRequest, HTTPInternalServerError  # noqa: E501
from cornice.resource import resource, view
from c2corg_api.views import cors_policy, to_json_dict
from c2corg_api.models.route import Route, schema_route
from c2corg_api.models.area import schema_listing_area
from shapely.geometry import shape
from pyproj import Transformer

log = logging.getLogger(__name__)

def validate_navitia_params(request, **kwargs):
    """Validates the required parameters for the Navitia API"""
    required_params = ['from', 'to', 'datetime', 'datetime_represents']

    for param in required_params:
        if param not in request.params:
            request.errors.add(
                'querystring',
                param,
                f'Paramètre {param} requis')


@resource(path='/navitia/journeys', cors_policy=cors_policy)
class NavitiaRest:

    def __init__(self, request, context=None):
        self.request = request

    @view(validators=[validate_navitia_params])
    def get(self):
        """
        Endpoint to retrieve trips from the Navitia API

        Required query string parameters:
        - from: starting coordinates (format: longitude;latitude)
        - to: arrival coordinates (format: longitude;latitude)
        - datetime: date and hour (format ISO 8601)
        - datetime_represents: 'departure' or 'arrival'
        """
        try:
            # Récupération de la clé API depuis les variables d'environnement
            api_key = os.getenv('NAVITIA_API_KEY')
            if not api_key:
                raise HTTPInternalServerError(
                    'Configuration API Navitia manquante')

            # Construction des paramètres
            params = {
                'from': self.request.params.get('from'),
                'to': self.request.params.get('to'),
                'datetime': self.request.params.get('datetime'),
                'datetime_represents': self.request.params.get('datetime_represents')  # noqa: E501
            }

            # Ajout des paramètres optionnels s'ils sont présents
            optional_params = [
                'max_duration_to_pt',
                'walking_speed',
                'bike_speed',
                'bss_speed',
                'car_speed',
                'forbidden_uris',
                'allowed_id',
                'first_section_mode',
                'last_section_mode',
                'max_walking_duration_to_pt',
                'max_nb_transfers',
                'min_nb_journeys',
                'max_bike_duration_to_pt',
                'max_bss_duration_to_pt',
                'max_car_duration_to_pt',
                'timeframe_duration',
                'max_walking_direct_path_duration',
                'wheelchair',
                'traveler_type',
                'data_freshness']

            for param in optional_params:
                if param in self.request.params:
                    params[param] = self.request.params.get(param)

            # Appel à l'API Navitia
            response = requests.get(
                'https://api.navitia.io/v1/journeys',
                params=params,
                headers={'Authorization': api_key},
                timeout=30
            )

            # Vérification du statut de la réponse
            if response.status_code == 401:
                raise HTTPInternalServerError(
                    'Authentication error with Navitia API')
            elif response.status_code == 400:
                raise HTTPBadRequest('Invalid parameters for Navitia API')
            elif response.status_code == 404:
                return {}
            elif not response.ok:
                raise HTTPInternalServerError(f'Navitia API error: {response.status_code}')  # noqa: E501

            # Retour des données JSON
            return response.json()

        except requests.exceptions.Timeout:
            raise HTTPInternalServerError(
                'Timeout when calling the Navitia API')
        except requests.exceptions.RequestException as e:
            raise HTTPInternalServerError(f'Network error: {str(e)}')
        except Exception as e:
            raise HTTPInternalServerError(f'Internal error: {str(e)}')


@resource(path='/navitia/journeyreachableroutes', cors_policy=cors_policy)
class NavitiaJourneyReachableRoutesRest:
    def __init__(self, request, context=None):
        self.request = request

    @view(validators=[])
    def get(self):
        validated = self.request.validated

        meta_params = {
            'offset': validated.get('offset', 0),
            'limit': validated.get('limit', LIMIT_DEFAULT),
            'lang': validated.get('lang')
        }

        journey_params = {
            'from': self.request.params.get('from'),
            'datetime': self.request.params.get('datetime'),
            'datetime_represents': self.request.params.get('datetime_represents'),
            'walking_speed': self.request.params.get('walking_speed'),
            'max_walking_duration_to_pt': self.request.params.get('max_walking_duration_to_pt'),
            'to': ''
        }

        query = build_reachable_route_query_with_waypoints(
            self.request.GET, meta_params)

        results = (
            query.all()
        )

        # manage areas for routes
        areas_id = set()
        for route, areas, waypoints in results:
            if areas is None:
                continue
            for area in areas:
                area_id = area.get("document_id")
                if area_id is not None:
                    areas_id.add(area_id)

        areas_objects = DBSession.query(Area).filter(
            Area.document_id.in_(areas_id)).all()

        areas_map = {area.document_id: area for area in areas_objects}

        # manage waypoints
        waypoints_id = set()
        for route, areas, waypoints in results:
            if waypoints is None:
                return

            for waypoint in waypoints:
                wp_id = waypoint.get("document_id")
                if wp_id is not None:
                    waypoints_id.add(wp_id)

        wp_objects = DBSession.query(Waypoint).filter(
            Waypoint.document_id.in_(waypoints_id)).all()

        log.warning("Number of NAVITIA journey queries : %d", len(wp_objects))

        navitia_wp_map = {wp.document_id: is_wp_journey_reachable(
            to_json_dict(wp, schema_waypoint), journey_params) for wp in wp_objects}

        routes = []
        for route, areas, waypoints in results:
            # check if a journey exists for route (at least one wp has a journey associated)
            journey_exists = False
            for wp in waypoints:
                wp_id = wp.get("document_id")
                journey_exists |= navitia_wp_map.get(wp_id)

            if journey_exists:
                json_areas = []
                if areas is None:
                    areas = []

                for area in areas:
                    area_obj = areas_map.get(area.get("document_id"))
                    if area_obj:
                        json_areas.append(to_json_dict(
                            area_obj, schema_listing_area))

                # assign JSON areas to the waypoint
                route.areas = json_areas
                wp_dict = to_json_dict(route, schema_route, True)
                routes.append(wp_dict)

        return {'documents': routes, 'total': len(routes)}


@resource(path='/navitia/journeyreachablewaypoints', cors_policy=cors_policy)
class NavitiaJourneyReachableWaypointsRest:
    def __init__(self, request, context=None):
        self.request = request

    @view(validators=[])
    def get(self):
        validated = self.request.validated

        meta_params = {
            'offset': validated.get('offset', 0),
            'limit': validated.get('limit', LIMIT_DEFAULT),
            'lang': validated.get('lang')
        }

        journey_params = {
            'from': self.request.params.get('from'),
            'datetime': self.request.params.get('datetime'),
            'datetime_represents': self.request.params.get('datetime_represents'),
            'walking_speed': self.request.params.get('walking_speed'),
            'max_walking_duration_to_pt': self.request.params.get('max_walking_duration_to_pt'),
            'to': ''
        }

        query = build_reachable_waypoints_query(
            self.request.GET, meta_params)

        results = (
            query.all()
        )

        # manage areas for waypoints
        areas_id = set()
        for waypoints, areas in results:
            if areas is None:
                continue
            for area in areas:
                area_id = area.get("document_id")
                if area_id is not None:
                    areas_id.add(area_id)

        areas_objects = DBSession.query(Area).filter(
            Area.document_id.in_(areas_id)).all()

        areas_map = {area.document_id: area for area in areas_objects}

        log.warning("Number of NAVITIA journey queries : %d", len(results))

        waypoints = []
        for waypoint, areas in results:
            # check if a journey exists for waypoint
            if is_wp_journey_reachable(to_json_dict(waypoint, schema_waypoint), journey_params):
                json_areas = []
                if areas is None:
                    areas = []

                for area in areas:
                    area_obj = areas_map.get(area.get("document_id"))
                    if area_obj:
                        json_areas.append(to_json_dict(
                            area_obj, schema_listing_area))

                # assign JSON areas to the waypoint
                waypoint.areas = json_areas
                wp_dict = to_json_dict(waypoint, schema_waypoint, True)
                waypoints.append(wp_dict)

        return {'documents': waypoints, 'total': len(waypoints)}

@resource(path='/navitia/isochronesreachableroutes', cors_policy=cors_policy)
class NavitiaIsochronesReachableRoutesRest:
    def __init__(self, request, context=None):
        self.request = request

    @view(validators=[])
    def get(self):
        validated = self.request.validated

        meta_params = {
            'offset': validated.get('offset', 0),
            'limit': validated.get('limit', LIMIT_DEFAULT),
            'lang': validated.get('lang')
        }

        isochrone_params = {
            'from': self.request.params.get('from'),
            'datetime': self.request.params.get('datetime'),
            'boundary_duration[]': self.request.params.get('boundary_duration'),
            'datetime_represents': self.request.params.get('datetime_represents')
        }

        query = build_reachable_route_query_with_waypoints(
            self.request.GET, meta_params)

        results = query.all()

        # manage areas for routes
        areas_id = set()
        for route, areas, waypoints in results:
            if areas is None:
                continue
            for area in areas:
                area_id = area.get("document_id")
                if area_id is not None:
                    areas_id.add(area_id)

        areas_objects = DBSession.query(Area).filter(
            Area.document_id.in_(areas_id)).all()

        areas_map = {area.document_id: area for area in areas_objects}

        response = get_navitia_isochrone(isochrone_params)
        
        routes = []
        geojson = ""
        # if isochrone found
        if (len(response["isochrones"]) > 0):
            geojson = response["isochrones"][0]["geojson"]
            isochrone_geom = shape(geojson)
            
            # manage waypoints
            waypoints_id = set()
            for route, areas, waypoints in results:
                if waypoints is None:
                    return

                for waypoint in waypoints:
                    wp_id = waypoint.get("document_id")
                    if wp_id is not None:
                        waypoints_id.add(wp_id)

            wp_objects = DBSession.query(Waypoint).filter(
                Waypoint.document_id.in_(waypoints_id)).all()

            navitia_wp_map = {wp.document_id: is_wp_in_isochrone(
                to_json_dict(wp, schema_waypoint), isochrone_geom) for wp in wp_objects}

            for route, areas, waypoints in results:
                # check if a journey exists for route (at least one wp has a journey associated)
                one_wp_in_isochrone = False
                for wp in waypoints:
                    wp_id = wp.get("document_id")
                    one_wp_in_isochrone |= navitia_wp_map.get(wp_id)

                if  one_wp_in_isochrone:
                    json_areas = []

                    if areas is None:
                        areas = []

                    for area in areas:
                        area_obj = areas_map.get(area.get("document_id"))
                        if area_obj:
                            json_areas.append(to_json_dict(
                                area_obj, schema_listing_area))

                    # assign JSON areas to the waypoint
                    route.areas = json_areas
                    route_dict = to_json_dict(route, schema_route, True)
                    routes.append(route_dict)

        return {'documents': routes, 'total': len(routes), 'isochron_geom': geojson}


@resource(path='/navitia/isochronesreachablewaypoints', cors_policy=cors_policy)
class NavitiaIsochronesReachableWaypointsRest:
    def __init__(self, request, context=None):
        self.request = request

    @view(validators=[])
    def get(self):
        validated = self.request.validated

        meta_params = {
            'offset': validated.get('offset', 0),
            'limit': validated.get('limit', LIMIT_DEFAULT),
            'lang': validated.get('lang')
        }

        isochrone_params = {
            'from': self.request.params.get('from'),
            'datetime': self.request.params.get('datetime'),
            'boundary_duration[]': self.request.params.get('boundary_duration'),
            'datetime_represents': self.request.params.get('datetime_represents')
        }

        query = build_reachable_waypoints_query(
            self.request.GET, meta_params)

        results = query.all()

        # manage areas for waypoints
        areas_id = set()
        for waypoints, areas in results:
            if areas is None:
                continue
            for area in areas:
                area_id = area.get("document_id")
                if area_id is not None:
                    areas_id.add(area_id)

        areas_objects = DBSession.query(Area).filter(
            Area.document_id.in_(areas_id)).all()

        areas_map = {area.document_id: area for area in areas_objects}

        response = get_navitia_isochrone(isochrone_params)
        
        waypoints = []
        geojson = ""
        # if isochrone found
        if (len(response["isochrones"]) > 0):
            geojson = response["isochrones"][0]["geojson"]
            isochrone_geom = shape(geojson)

            for waypoint, areas in results:
                # check if wp is in isochrone
                if is_wp_in_isochrone(to_json_dict(waypoint, schema_waypoint), isochrone_geom):
                    json_areas = []
                    if areas is None:
                        areas = []

                    for area in areas:
                        area_obj = areas_map.get(area.get("document_id"))
                        if area_obj:
                            json_areas.append(to_json_dict(
                                area_obj, schema_listing_area))

                    # assign JSON areas to the waypoint
                    waypoint.areas = json_areas
                    wp_dict = to_json_dict(waypoint, schema_waypoint, True)
                    waypoints.append(wp_dict)

        return {'documents': waypoints, 'total': len(waypoints), "isochron_geom": geojson}


def is_wp_journey_reachable(waypoint, journey_params):
    # enhance journey params with the 'to' parameter, from the waypoint geometry.
    geom = shape(json.loads(waypoint.get("geometry").get("geom")))

    src_epsg = 3857
    transformer = Transformer.from_crs(
        f"EPSG:{src_epsg}", "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(geom.x, geom.y)

    journey_params['to'] = f"{lon};{lat}"

    destination_coverage = get_coverage(lon, lat)

    try:
        # Récupération de la clé API depuis les variables d'environnement
        api_key = os.getenv('NAVITIA_API_KEY')
        if not api_key:
            return False

        response = {}

        if (destination_coverage):
            # Appel à l'API Navitia Journey with coverage
            response = requests.get(
                f'https://api.navitia.io/v1/coverage/{destination_coverage}/journeys',
                params=journey_params,
                headers={'Authorization': api_key},
                timeout=30
            )
        else:
            # Appel à l'API Navitia Journey
            response = requests.get(
                'https://api.navitia.io/v1/journeys',
                params=journey_params,
                headers={'Authorization': api_key},
                timeout=30
            )

        # Vérification du statut de la réponse
        if response.status_code == 401:
            return False
        elif response.status_code == 400:
            return False
        elif response.status_code == 404:
            return False
        elif not response.ok:
            return False

        # make sure the waypoint is reachable if at least one journey's departure date time is the same day as the day in journey_params
        for journey in response.json()['journeys']:
            journey_day = int(journey['departure_date_time'][6:8])
            param_day = int(journey_params['datetime'][6:8])
            if journey_day == param_day:
                return True
            
        return False

    except requests.exceptions.Timeout:
        return False
    except requests.exceptions.RequestException as e:
        return False
    except Exception as e:
        return False


def get_navitia_isochrone(isochrone_params):
    lon = isochrone_params.get("from").split(";")[0]
    lat = isochrone_params.get("from").split(";")[1]
    source_coverage = get_coverage(lon, lat)

    try:
        # Récupération de la clé API depuis les variables d'environnement
        api_key = os.getenv('NAVITIA_API_KEY')
        if not api_key:
            raise HTTPInternalServerError(
                'Configuration API Navitia manquante')

        response = {}

        if (source_coverage):
            # Appel à l'API Navitia Journey with coverage
            response = requests.get(
                f'https://api.navitia.io/v1/coverage/{source_coverage}/isochrones',
                params=isochrone_params,
                headers={'Authorization': api_key},
                timeout=30
            )
        else:
            # can't call isochrones api without coverage
            raise HTTPInternalServerError(
                'Coverage not found for source')

    # Vérification du statut de la réponse
        if response.status_code == 401:
            raise HTTPInternalServerError(
                'Authentication error with Navitia API')
        elif response.status_code == 400:
            raise HTTPBadRequest('Invalid parameters for Navitia API')
        elif response.status_code == 404:
            return {}
        elif not response.ok:
            raise HTTPInternalServerError(f'Navitia API error: {response.status_code}')  # noqa: E501

        # Retour des données JSON
        return response.json()

    except requests.exceptions.Timeout:
        raise HTTPInternalServerError(
            'Timeout when calling the Navitia API')
    except requests.exceptions.RequestException as e:
        raise HTTPInternalServerError(f'Network error: {str(e)}')
    except Exception as e:
        raise HTTPInternalServerError(f'Internal error: {str(e)}')


def is_wp_in_isochrone(waypoint, isochrone_geom):
    # get lon & lat
    geom = shape(json.loads(waypoint.get("geometry").get("geom")))

    src_epsg = 3857
    transformer = Transformer.from_crs(
        f"EPSG:{src_epsg}", "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(geom.x, geom.y)
    pt = Point(lon, lat)
    
    return isochrone_geom.contains(pt)
    