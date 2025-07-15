import os
import requests
from pyramid.httpexceptions import HTTPBadRequest, HTTPInternalServerError, HTTPNotFound
from cornice.resource import resource, view
from c2corg_api.views import cors_policy


def validate_navitia_params(request, **kwargs):
    """Validates the required parameters for the Navitia API"""
    required_params = ['from', 'to', 'datetime', 'datetime_represents']
    
    for param in required_params:
        if param not in request.params:
            request.errors.add('querystring', param, f'Paramètre {param} requis')


@resource(path='/navitia/journeys', cors_policy=cors_policy)
class NavitiaRest:
    
    def __init__(self, request):
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
                raise HTTPInternalServerError('Configuration API Navitia manquante')

            # Construction des paramètres
            params = {
                'from': self.request.params.get('from'),
                'to': self.request.params.get('to'),
                'datetime': self.request.params.get('datetime'),
                'datetime_represents': self.request.params.get('datetime_represents')
            }

            # Ajout des paramètres optionnels s'ils sont présents
            optional_params = [
                'max_duration_to_pt', 'walking_speed', 'bike_speed', 
                'bss_speed', 'car_speed', 'forbidden_uris', 'allowed_id',
                'first_section_mode', 'last_section_mode', 'max_walking_duration_to_pt','max_nb_transfers', 'min_nb_journeys',
                'max_bike_duration_to_pt', 'max_bss_duration_to_pt', 'max_car_duration_to_pt', 'timeframe_duration',
                'max_walking_direct_path_duration',
                'wheelchair', 'traveler_type', 'data_freshness'
            ]
            
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
                raise HTTPInternalServerError('Authentication error with Navitia API')
            elif response.status_code == 400:
                raise HTTPBadRequest('Invalid parameters for Navitia API')
            elif response.status_code == 404:
                return {}
            elif not response.ok:
                raise HTTPInternalServerError(f'Navitia API error: {response.status_code}')

            # Retour des données JSON
            return response.json()

        except requests.exceptions.Timeout:
            raise HTTPInternalServerError('Timeout when calling the Navitia API')
        except requests.exceptions.RequestException as e:
            raise HTTPInternalServerError(f'Network error: {str(e)}')
        except Exception as e:
            raise HTTPInternalServerError(f'Internal error: {str(e)}')