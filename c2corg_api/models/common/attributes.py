# coding: utf-8
default_langs = ['fr', 'it', 'de', 'en', 'es', 'ca', 'eu', 'sl', 'zh']
langs_priority = ['fr', 'en', 'it', 'de', 'es', 'ca', 'eu', 'sl', 'zh']

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
    'via_ferrata',
    'slacklining'
]

waypoint_types = [
    'summit',               # sommet
    'pass',                 # col
    'lake',                 # lac
    'waterfall',            # cascade
    'locality',             # lieu-dit (v5: vallon)
    'bisse',                # bisse
    'canyon',               # canyon

    'access',               # acces

    'climbing_outdoor',     # site d'escalade
    'climbing_indoor',      # S.A.E.

    'hut',                  # refuge
    'gite',                 # gite
    'shelter',              # abri
    'bivouac',              # bivouac
    'camp_site',            # camping
    'base_camp',            # camp de base

    'local_product',        # produit locaux

    'paragliding_takeoff',  # deco
    'paragliding_landing',  # attero

    'cave',                 # grotte
    'waterpoint',           # point d'eau/source

    'weather_station',      # station meteo
    'webcam',               # webcam
    'virtual',              # sur-WP virtuel

    'slackline_spot',

    'misc',                 # divers
]

climbing_outdoor_types = [
    'single',
    'multi',
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
    'boat'
]

product_types = [
    'farm_sale',  # vente chez le producteur
    'restaurant',
    'grocery',
    'bar',
    'sport_shop'
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
    'good service',      # service regulier
    'seasonal service',  # service saisonnier
    'poor service',      # service reduit
    'nearby service',    # service a proximite
    'unknown service',    # service inconnu
    'no service'         # pas de service
]

# Cotation deco/attero
paragliding_ratings = [
    '1',
    '2',
    '3',
    '4'
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
    '5a+',
    '5b',
    '5b+',
    '5c',
    '5c+',
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
    '9b',
    '9b+',
    '9c',
    '9c+'
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

route_types = [
    'return_same_way',  # aller-retour (descente en rappel dans la voie)
    'loop',             # boucle avec retour au pied de la voie (descente en
                        # rappel dans une autre voie)
    'loop_hut',         # boucle avec retour au refuge
    'traverse',         # traversee
    'raid',             # raid
    'expedition'        # expe
]

route_duration_types = [
    '1',
    '2',
    '3',
    '4',
    '5',
    '6',
    '7',
    '8',
    '9',
    '10',
    '10+'
]

glacier_gear_types = [
    'no',
    'glacier_safety_gear',  # materiel de securite sur glacier
    'crampons_spring',      # crampons en debut de saison
    'crampons_req',         # crampons indispensable
    'glacier_crampons'      # crampons + materiel de securite sur glacier
]

route_configuration_types = [
    'edge',
    'pillar',
    'face',
    'corridor',
    'goulotte',
    'glacier'
]

ski_ratings = [
    '1.1',
    '1.2',
    '1.3',
    '2.1',
    '2.2',
    '2.3',
    '3.1',
    '3.2',
    '3.3',
    '4.1',
    '4.2',
    '4.3',
    '5.1',
    '5.2',
    '5.3',
    '5.4',
    '5.5',
    '5.6'
]

labande_ski_ratings = [
    'S1',
    'S2',
    'S3',
    'S4',
    'S5',
    'S6',
    'S7'
]

global_ratings = [
    'F',
    'F+',
    'PD-',
    'PD',
    'PD+',
    'AD-',
    'AD',
    'AD+',
    'D-',
    'D',
    'D+',
    'TD-',
    'TD',
    'TD+',
    'ED-',
    'ED',
    'ED+',
    'ED4',
    'ED5',
    'ED6',
    'ED7'
]

engagement_ratings = [
    'I',
    'II',
    'III',
    'IV',
    'V',
    'VI'
]

risk_ratings = [
    'X1',
    'X2',
    'X3',
    'X4',
    'X5'
]

ice_ratings = [
    '1',
    '2',
    '3',
    '3+',
    '4',
    '4+',
    '5',
    '5+',
    '6',
    '6+',
    '7',
    '7+'
]

mixed_ratings = [
    'M1',
    'M2',
    'M3',
    'M3+',
    'M4',
    'M4+',
    'M5',
    'M5+',
    'M6',
    'M6+',
    'M7',
    'M7+',
    'M8',
    'M8+',
    'M9',
    'M9+',
    'M10',
    'M10+',
    'M11',
    'M11+',
    'M12',
    'M12+'
]

exposition_rock_ratings = [
    'E1',
    'E2',
    'E3',
    'E4',
    'E5',
    'E6'
]

aid_ratings = [
    'A0',
    'A0+',
    'A1',
    'A1+',
    'A2',
    'A2+',
    'A3',
    'A3+',
    'A4',
    'A4+',
    'A5',
    'A5+'
]

via_ferrata_ratings = [
    'K1',
    'K2',
    'K3',
    'K4',
    'K5',
    'K6'
]

hiking_ratings = [
    'T1',
    'T2',
    'T3',
    'T4',
    'T5'
]

snowshoe_ratings = [
    'R1',
    'R2',
    'R3',
    'R4',
    'R5'
]

mtb_up_ratings = [
    'M1',
    'M2',
    'M3',
    'M4',
    'M5'
]

mtb_down_ratings = [
    'V1',
    'V2',
    'V3',
    'V4',
    'V5'
]

map_editors = [
    'IGN',
    'Swisstopo',
    'Escursionista'
]

map_scales = [
    '25000',
    '50000',
    '100000'
]

area_types = [
    'range',
    'admin_limits',
    'country'
]

frequentation_types = [
    'quiet',
    'some',
    'crowded',
    'overcrowded'
]

access_conditions = [
    'cleared',
    'snowy',
    'closed_snow',
    'closed_cleared'
]

lift_status = [
    'open',
    'closed'
]

condition_ratings = [
    'excellent',
    'good',
    'average',
    'poor',
    'awful'
]

snow_quality_ratings = [
    'excellent',
    'good',
    'average',
    'poor',
    'awful'
]

snow_quantity_ratings = [
    'excellent',
    'good',
    'average',
    'poor',
    'awful'
]

glacier_ratings = [
    'easy',
    'possible',
    'difficult',
    'impossible'
]

avalanche_signs = [
    'no',
    'danger_sign',
    'recent_avalanche',
    'natural_avalanche',
    'accidental_avalanche'
]

hut_status = [
    'open_guarded',
    'open_non_guarded',
    'closed_hut'
]

image_categories = [
    'landscapes',
    'detail',
    'action',
    'track',
    'rise',
    'descent',
    'topo',
    'people',
    'fauna',
    'flora',
    'nivology',
    'geology',
    'hut',
    'equipment',
    'book',
    'help',
    'misc'
]

image_types = [
    'collaborative',
    'personal',
    'copyright'
]

user_categories = [
    'amateur',
    'mountain_guide',
    'mountain_leader',
    'ski_instructor',
    'climbing_instructor',
    'mountainbike_instructor',
    'paragliding_instructor',
    'hut_warden',
    'ski_patroller',
    'avalanche_forecaster',
    'club',
    'institution'
]

quality_types = [
    'empty',
    'draft',
    'medium',
    'fine',
    'great'
]

custodianship_types = [
    'accessible_when_wardened',
    'always_accessible',
    'key_needed',
    'no_warden'
]

article_categories = [
    'mountain_environment',
    'gear',
    'technical',
    'topoguide_supplements',
    'soft_mobility',
    'expeditions',
    'stories',
    'c2c_meetings',
    'tags',
    'site_info',
    'association'
]

article_types = [
    'collab',
    'personal'
]

feed_change_types = [
    'created',
    'updated',
    'added_photos'
]

book_types = [
    'topo',
    'environment',
    'historical',
    'biography',
    'photos-art',
    'novel',
    'technics',
    'tourism',
    'magazine'
]

mailinglists = [
    'avalanche',
    'lawinen',
    'valanghe',
    'avalanche.en',
    'meteofrance-38',
    'meteofrance-74',
    'meteofrance-73',
    'meteofrance-04',
    'meteofrance-05',
    'meteofrance-06',
    'meteofrance-31',
    'meteofrance-64',
    'meteofrance-65',
    'meteofrance-66',
    'meteofrance-09',
    'meteofrance-andorre',
    'meteofrance-2a',
    'meteofrance-2b',
    'aran',
    'catalunya'
]

event_activities = [
    'sport_climbing',
    'multipitch_climbing',
    'alpine_climbing',
    'snow_ice_mixed',
    'ice_climbing',
    'skitouring',
    'other'
]

event_types = [
    'avalanche',
    'stone_ice_fall',
    'ice_cornice_collapse',
    'person_fall',
    'crevasse_fall',
    'physical_failure',
    'injury_without_fall',
    'blocked_person',
    'weather_event',
    'safety_operation',
    'critical_situation',
    'other'
]

author_statuses = [
    'primary_impacted',
    'secondary_impacted',
    'internal_witness',
    'external_witness'
]

activity_rates = [
    'activity_rate_y5',
    'activity_rate_m2',
    'activity_rate_w1'
]

genders = [
    'male',
    'female'
]

previous_injuries = [
    'no',
    'previous_injuries_2',
    'previous_injuries_3'
]

severities = [
    'severity_no',
    '1d_to_3d',
    '4d_to_1m',
    '1m_to_3m',
    'more_than_3m',
]

autonomies = [
    'non_autonomous',
    'autonomous',
    'expert',
]

supervision = [
    'no_supervision',
    'federal_supervision',
    'professional_supervision'
]

qualification = [
    'federal_supervisor',
    'federal_trainer',
    'professional_diploma'
]

avalanche_levels = [
    'level_1',
    'level_2',
    'level_3',
    'level_4',
    'level_5',
    'level_na'
]

avalanche_slopes = [
    'slope_lt_30',
    'slope_30_35',
    'slope_35_40',
    'slope_40_45',
    'slope_gt_45'
]

slackline_types = [
    'slackline',
    'highline',
    'waterline'
]
