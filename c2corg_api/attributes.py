default_cultures = ['ca', 'de', 'en', 'es', 'eu', 'fr', 'it']

activities = [
    'skitouring',
    'snow_ice_mixed',
    'mountain_climbing',
    'rock_climbing',
    'ice_climbing',
    'hiking',
    'snowshoeing',
    'paragliding',
    'mountain_biking',
    'via_ferrata'
]

waypoint_types = [
    'virtuel',              # sur-WP virtuel
    'summit',               # sommet
    'pass',                 # col
    'lake',                 # lac
    'bisse',                # bisse
    'waterfall',            # cascade
    'cave',                 # grotte
    'pit',                  # gouffre
    'locality',             # lieu-dit (v5: vallon)
    'confluence',           # confluent
    'glacier',              # glacier
    'randkluft',            # rimaye
    'source',               # source
    'cliff',                # falaise
    'divers',               # divers

    'climbing_outdoor',     # site de couenne/bloc
    'climbing_indoor',      # S.A.E.

    'gite',                 # gite
    'camp_site',            # camping
    'hut',                  # refuge
    'shelter',              # abri
    'bivouac',              # bivouac

    'base_camp',            # camp de base
    'access',               # acces

    'local_product',        # produit locaux
    'sport_shop',           # magasin de sport

    'paragliding_takeoff',  # deco
    'paragliding_landing',  # attero

    'weather_station',      # station meteo
    'webcam',               # webcam
]

climbing_outdoor_types = [
    'couenne',
    'bloc',
    'psicobloc'
]

climbing_indoor_types = [
    'pitch',
    'bloc'
]

public_transportation_types = [
    'train',
    'bus',
    'service_on_demand',
    'boat',
    'cable_car'
]

product_types = [
    'farm_sale',  # vente chez le producteur
    'restaurant',
    'grocery',
    'bar'
]

ground_types = [
    'prairie',
    'scree',  # eboulis
    'snow'
]

weather_station_types = [
    'temperature',
    'wind_speed',
    'wind_direction',
    'humidity',
    'pressure',
    'precipitation',  # precipitations (sans rechauffeur)
    'precipitation_heater',  # precipitations (avec rechauffeur)
    'snow_height',
    'insolation'
]

rain_proof_types = [
    'exposed',
    'partly_protected',
    'protected',
    'inside'
]

public_transportation_ratings = [
    'good',      # service regulier
    'seasonal',  # service saisonnier
    'poor',      # service reduit
    'near',      # service a proximite
    'no'         # pas de service
]

# Cotation deco/attero
paragliding_ratings = [
    '1',
    '2',
    '3',
    '4',
    '5',
    '6'
]

children_proof_types = [
    'very_safe',
    'safe',
    'dangerous',
    'very_dangerous'
]

snow_clearance_ratings = [
    'often',
    'sometimes',
    'progressive',
    'naturally',
    'closed_in_winter',
    'non_applicable'
]

exposition_ratings = [
    'E1',
    'E2',
    'E3',
    'E4'
]

rock_types = [
    'basalte',
    'calcaire',
    'conglomerat',
    'craie',
    'gneiss',
    'gres',
    'granit',
    'migmatite',
    'mollasse_calcaire',
    'pouding',
    'quartzite',
    'rhyolite',
    'schiste',
    'trachyte',
    'artificial'
]

orientation_types = [
    'N',
    'NE',
    'E',
    'SE',
    'S',
    'SW',
    'W',
    'NW'
]

months = [
    'jan',
    'feb',
    'mar',
    'apr',
    'may',
    'jun',
    'jul',
    'aug',
    'sep',
    'oct',
    'nov',
    'dec'
]

custodianship_types = [
    'yes_open',       # ferme hors gardiennage
    'yes_closed',     # ouvert hors gardiennage
    'key',            # cle a recuperer
    'no'              # non gardienne
]

parking_fee_types = [
    'yes',
    'seasonal',
    'no'
]

climbing_styles = [
    'slab',             # dalle
    'vertical',         # vertical
    'overhang',         # devers/surplomb
    'roof',             # toit
    'small_pillar',     # colonnettes
    'crack_dihedral'    # fissure/diedre
]

access_times = [
    '1min',
    '5min',
    '10min',
    '15min',
    '20min',
    '30min',
    '45min',
    '1h',
    '1h30',
    '2h',
    '2h30',
    '3h',
    '3h+',
]

climbing_ratings = [
    '2',
    '3a',
    '3b',
    '3c',
    '4a',
    '4b',
    '4c',
    '5a',
    '5b',
    '5c',
    '6a',
    '6a+',
    '6b',
    '6b+',
    '6c',
    '6c+',
    '7a',
    '7a+',
    '7b',
    '7b+',
    '7c',
    '7c+',
    '8a',
    '8a+',
    '8b',
    '8b+',
    '8c',
    '8c+',
    '9a',
    '9a+',
    '9b'
]

equipment_ratings = [
    'P1',
    'P1+',
    'P2',
    'P2+',
    'P3',
    'P3+',
    'P4',
    'P4+'
]
