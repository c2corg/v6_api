import json
import logging
import os
import requests
from c2corg_api.models import DBSession
from c2corg_api.models.area import Area
from c2corg_api.models.utils import wkb_to_shape
from c2corg_api.models.waypoint import Waypoint, schema_waypoint
from c2corg_api.views.coverage import get_coverage
from c2corg_api.views.document import LIMIT_DEFAULT
from c2corg_api.views.waypoint import build_reachable_waypoints_query
from c2corg_api.views.route import build_reachable_route_query_with_waypoints
from shapely.geometry import Point
from pyramid.httpexceptions import HTTPBadRequest, HTTPInternalServerError  # noqa: E501
from cornice.resource import resource, view
from c2corg_api.views import cors_policy, to_json_dict
from c2corg_api.models.route import schema_route
from c2corg_api.models.area import schema_listing_area
from shapely.geometry import shape
from pyproj import Transformer

log = logging.getLogger(__name__)

# When editing these constants, make sure to edit them in the front too
# (itinevert-service)
MAX_ROUTE_THRESHOLD = 50
MAX_TRIP_DURATION = 240
MIN_TRIP_DURATION = 20


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


def validate_journey_reachable_params(request, **kwargs):
    """Validates the required parameters for the journey reachable doc route"""
    required_params = ['from', 'datetime', 'datetime_represents',
                       'walking_speed', 'max_walking_duration_to_pt']

    for param in required_params:
        if param not in request.params:
            request.errors.add(
                'querystring',
                param,
                f'Paramètre {param} requis')


@resource(path='/navitia/journeyreachableroutes', cors_policy=cors_policy)
class NavitiaJourneyReachableRoutesRest:
    def __init__(self, request, context=None):
        self.request = request

    @view(validators=[validate_journey_reachable_params])
    def get(self):
        """
        Get all routes matching filters in params, that are reachable
        (means there exists a Navitia journey for at least one of
        their waypoints of type access).

        NOTE : the number of routes after applying filters,
        has to be < MAX_ROUTE_THRESHOLD,
        to reduce number of queries towards Navitia journey API
        """
        meta_params = extract_meta_params(self.request)

        journey_params = extract_journey_params(self.request)

        query = build_reachable_route_query_with_waypoints(
            self.request.GET, meta_params)

        results = (
            query.all()
        )

        # /!\ IMPORTANT
        # Before doing any further computations,
        # make sure the number of routes don't go above threshold.
        # The Itinevert UI doesn't allow that,
        # but a user could query the api with wrong parameters...
        if len(results) > MAX_ROUTE_THRESHOLD:
            raise HTTPBadRequest(
                "Couldn't proceed with computation : Too much routes found."
            )

        areas_map = collect_areas_from_results(results, 1)

        wp_objects = collect_waypoints_from_results(results)

        log.info("Number of NAVITIA journey queries : %d", len(wp_objects))

        navitia_wp_map = {
            wp.document_id: is_wp_journey_reachable(
                to_json_dict(wp, schema_waypoint), journey_params
            ) for wp in wp_objects}

        routes = []
        for route, areas, waypoints in results:
            # check if a journey exists for route
            # (at least one wp has a journey associated)
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

    @view(validators=[validate_journey_reachable_params])
    def get(self):
        """
        Get all waypoints matching filters in params, that are reachable
        (means there exists a Navitia journey).
        NOTE : waypoints should be filtered with one area,
        to reduce the number of queries towards Navitia journey API.
        """
        meta_params = extract_meta_params(self.request)

        journey_params = extract_journey_params(self.request)

        areas = None
        try:
            areas = self.request.GET['a'].split(",")
        except Exception:
            areas = None

        # Normalize: allow single value or list
        if areas is None:
            raise HTTPBadRequest('Missing filter : area is required')
        elif isinstance(areas, list):
            if len(areas) > 1:
                raise HTTPBadRequest('Only one filtering area is allowed')

        query = build_reachable_waypoints_query(
            self.request.GET, meta_params)

        results = (
            query.all()
        )

        areas_map = collect_areas_from_results(results, 1)

        log.info("Number of NAVITIA journey queries : %d", len(results))

        waypoints = []
        for waypoint, areas in results:
            # check if a journey exists for waypoint
            if is_wp_journey_reachable(
                to_json_dict(waypoint, schema_waypoint), journey_params
            ):
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


def validate_isochrone_reachable_params(request, **kwargs):
    """Validates the required parameters
    for the isochrone reachable doc route"""
    required_params = ['from', 'datetime',
                       'datetime_represents', 'boundary_duration']

    for param in required_params:
        if param not in request.params:
            request.errors.add(
                'querystring',
                param,
                f'Paramètre {param} requis')


@resource(path='/navitia/isochronesreachableroutes', cors_policy=cors_policy)
class NavitiaIsochronesReachableRoutesRest:
    def __init__(self, request, context=None):
        self.request = request

    @view(validators=[validate_isochrone_reachable_params])
    def get(self):
        """
        Get all routes matching filters in params, that have at least
        one waypoint of type access that is inside the isochron.
        The isochron is created by querying navitia api
        with specific parameters, see validate_isochrone_reachable_params func
        """
        meta_params = extract_meta_params(self.request)

        isochrone_params = extract_isochrone_params(self.request)

        query = build_reachable_route_query_with_waypoints(
            self.request.GET, meta_params)

        results = query.all()

        areas_map = collect_areas_from_results(results, 1)

        response = get_navitia_isochrone(isochrone_params)

        routes = []
        geojson = ""
        # if isochrone found
        if (len(response["isochrones"]) > 0):
            geojson = response["isochrones"][0]["geojson"]
            isochrone_geom = shape(geojson)

            wp_objects = collect_waypoints_from_results(results)

            navitia_wp_map = {wp.document_id: is_wp_in_isochrone(
                to_json_dict(wp, schema_waypoint), isochrone_geom
            ) for wp in wp_objects}

            for route, areas, waypoints in results:
                # check if a journey exists for route
                # (at least one wp has a journey associated)
                one_wp_in_isochrone = False
                for wp in waypoints:
                    wp_id = wp.get("document_id")
                    one_wp_in_isochrone |= navitia_wp_map.get(wp_id)

                if one_wp_in_isochrone:
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

        return {
            'documents': routes,
            'total': len(routes),
            'isochron_geom': geojson
        }


@resource(
    path='/navitia/isochronesreachablewaypoints',
    cors_policy=cors_policy
)
class NavitiaIsochronesReachableWaypointsRest:
    def __init__(self, request, context=None):
        self.request = request

    @view(validators=[validate_isochrone_reachable_params])
    def get(self):
        """
        Get all waypoints matching filters in params,
        that are inside the isochron.
        The isochron is created by querying navitia api
        with specific parameters, see validate_isochrone_reachable_params func
        """
        meta_params = extract_meta_params(self.request)

        isochrone_params = extract_isochrone_params(self.request)

        query = build_reachable_waypoints_query(
            self.request.GET, meta_params)

        results = query.all()

        # manage areas for waypoints
        areas_map = collect_areas_from_results(results, 1)

        response = get_navitia_isochrone(isochrone_params)

        waypoints = []
        geojson = ""
        # if isochrone found
        if (len(response["isochrones"]) > 0):
            geojson = response["isochrones"][0]["geojson"]
            isochrone_geom = shape(geojson)

            for waypoint, areas in results:
                # check if wp is in isochrone
                if is_wp_in_isochrone(
                    to_json_dict(waypoint, schema_waypoint), isochrone_geom
                ):
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

        return {
            'documents': waypoints,
            'total': len(waypoints),
            "isochron_geom": geojson
        }


@resource(path='/navitia/areainisochrone', cors_policy=cors_policy)
class AreaInIsochroneRest:
    def __init__(self, request, context=None):
        self.request = request

    @view(validators=[])
    def post(self):
        """
        returns all areas that are inside
        or that intersects an isochrone geometry

        make sure the geom_detail in body is epsg:3857
        """
        polygon = shape(json.loads(json.loads(
            self.request.body)['geom_detail']))

        query = (
            DBSession.query(Area)
        )

        results = query.all()

        areas = []

        for area in results:
            if (polygon.intersects(wkb_to_shape(area.geometry.geom_detail))):
                areas.append(area.document_id)

        return areas


def is_wp_journey_reachable(waypoint, journey_params):
    """
    Query the navitia Journey api and returns true
    if the waypoint is reachable (at least one journey has been found)
    NOTE : the journey's departure time has to be
    the same day as the datetime's day in journey_params
    """
    # enhance journey params with the 'to' parameter,
    # from the waypoint geometry.
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
                f'https://api.navitia.io/v1/coverage/{destination_coverage}/journeys',  # noqa: E501
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

        # make sure the waypoint is reachable if at least one journey's
        # departure date time is the same day as the day in journey_params
        for journey in response.json()['journeys']:
            journey_day = int(journey['departure_date_time'][6:8])
            param_day = int(journey_params['datetime'][6:8])
            if journey_day == param_day:
                return True

        return False

    except requests.exceptions.Timeout:
        return False
    except requests.exceptions.RequestException:
        return False
    except Exception:
        return False


def get_navitia_isochrone(isochrone_params):
    """
    Query the navitia Isochrones api, and returns the isochrone object
    """
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
                f'https://api.navitia.io/v1/coverage/{source_coverage}/isochrones',  # noqa: E501
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
    """
    Returns true if waypoints is contained in isochrone_geom
    """
    # get lon & lat
    geom = shape(json.loads(waypoint.get("geometry").get("geom")))

    src_epsg = 3857
    transformer = Transformer.from_crs(
        f"EPSG:{src_epsg}", "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(geom.x, geom.y)
    pt = Point(lon, lat)

    return isochrone_geom.contains(pt)


def extract_meta_params(request):
    """
    Extract meta parameters such as offset, limit and lang
    """
    v = request.validated
    return {
        'offset': v.get('offset', 0),
        'limit': v.get('limit', LIMIT_DEFAULT),
        'lang': v.get('lang'),
    }


def extract_journey_params(request):
    """
    Extract parameters for journey query
    """
    return {
        'from': request.params.get('from'),
        'datetime': request.params.get('datetime'),
        'datetime_represents': request.params.get('datetime_represents'),
        'walking_speed': request.params.get('walking_speed'),
        'max_walking_duration_to_pt': request.params.get('max_walking_duration_to_pt'),  # noqa: E501
        'to': ''
    }


def extract_isochrone_params(request):
    """
    Extract parameters for isochrone query

    NOTE : the boundary duration is bounded by constants
        MAX_TRIP_DURATION and MIN_TRIP_DURATION
    if the boundary duration goes beyond limits,
        it is set to the limit it goes past.
    """
    params = {
        'from': request.params.get('from'),
        'datetime': request.params.get('datetime'),
        'boundary_duration[]': request.params.get('boundary_duration'),
        'datetime_represents': request.params.get('datetime_represents')
    }
    # normalize boundary
    bd = params['boundary_duration[]']
    if len(bd.split(",")) == 1:
        duration = int(bd)
        params['boundary_duration[]'] = max(
            min(
                duration,
                MAX_TRIP_DURATION * 60
            ),
            MIN_TRIP_DURATION * 60
        )
    return params


def collect_areas_from_results(results, area_index):
    """
    Extract all area document_ids from results, load Area objects from DB,
    and return {document_id: Area}.
    """
    area_ids = set()

    for row in results:
        areas = row[area_index]

        if not areas:
            continue

        for area in areas:
            doc_id = area.get("document_id")
            if doc_id:
                area_ids.add(doc_id)

    area_objects = DBSession.query(Area).filter(
        Area.document_id.in_(area_ids)
    ).all()

    return {a.document_id: a for a in area_objects}


def collect_waypoints_from_results(results):
    """
    Extract all waypoint document_ids from results,
    load Waypoint objects from DB,
    and return {document_id: Waypoint}.
    """
    wp_ids = set()

    for route, areas, waypoints in results:
        if not waypoints:
            continue

        for wp in waypoints:
            doc_id = wp.get("document_id")
            if doc_id:
                wp_ids.add(doc_id)

    wp_objects = DBSession.query(Waypoint).filter(
        Waypoint.document_id.in_(wp_ids)
    ).all()

    return {wp for wp in wp_objects}
