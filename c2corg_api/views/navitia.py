import os
import requests
from pyramid.httpexceptions import HTTPBadRequest, HTTPInternalServerError
from cornice.resource import resource, view
from c2corg_api.views import cors_policy


def validate_navitia_params(request, **kwargs):
    """Valide les paramètres requis pour l'API Navitia"""
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
        Endpoint pour récupérer les trajets depuis l'API Navitia
        
        Paramètres query string requis:
        - from: coordonnées de départ (format: longitude;latitude)
        - to: coordonnées d'arrivée (format: longitude;latitude) 
        - datetime: date et heure (format ISO 8601)
        - datetime_represents: 'departure' ou 'arrival'
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
                'first_section_mode', 'last_section_mode', 'max_walking_duration_to_pt',
                'max_bike_duration_to_pt', 'max_bss_duration_to_pt', 'max_car_duration_to_pt',
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
                raise HTTPInternalServerError('Erreur d\'authentification avec l\'API Navitia')
            elif response.status_code == 400:
                raise HTTPBadRequest('Paramètres invalides pour l\'API Navitia')
            elif not response.ok:
                raise HTTPInternalServerError(f'Erreur API Navitia: {response.status_code}')

            # Retour des données JSON
            return response.json()

        except requests.exceptions.Timeout:
            raise HTTPInternalServerError('Timeout lors de l\'appel à l\'API Navitia')
        except requests.exceptions.RequestException as e:
            raise HTTPInternalServerError(f'Erreur réseau: {str(e)}')
        except Exception as e:
            raise HTTPInternalServerError(f'Erreur interne: {str(e)}')