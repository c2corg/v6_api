# Common attributes settings used by most waypoint types
DEFAULT_FIELDS = [
    'locales.title',
    'locales.summary',
    'locales.description',
    'geometry.geom',
    'elevation',
    'maps_info',
    'quality'
]
DEFAULT_REQUIRED = [
    'locales',
    'locales.title',
    'geometry',
    'geometry.geom',
    'elevation'
]
DEFAULT_LISTING = [
    'locales.title',
    'locales.summary',
    'geometry.geom',
    'elevation',
    'quality',
    'waypoint_type'
]
DEFAULT_ATTRIBUTES_SETTINGS = {
    'fields': DEFAULT_FIELDS,
    'required': DEFAULT_REQUIRED,
    'listing': DEFAULT_LISTING
}

fields_waypoint = {
    'virtual': DEFAULT_ATTRIBUTES_SETTINGS,
    'summit': {
        'fields': DEFAULT_FIELDS + [
            'prominence'
        ],
        'required': DEFAULT_REQUIRED,
        'listing': DEFAULT_LISTING
    },
    'pass': DEFAULT_ATTRIBUTES_SETTINGS,
    'lake': DEFAULT_ATTRIBUTES_SETTINGS,
    'bisse': DEFAULT_ATTRIBUTES_SETTINGS,
    'waterfall': DEFAULT_ATTRIBUTES_SETTINGS,
    'cave': DEFAULT_ATTRIBUTES_SETTINGS,
    'locality': DEFAULT_ATTRIBUTES_SETTINGS,
    'waterpoint': DEFAULT_ATTRIBUTES_SETTINGS,
    'canyon': DEFAULT_ATTRIBUTES_SETTINGS,
    'misc': DEFAULT_ATTRIBUTES_SETTINGS,
    'climbing_outdoor': {
        'fields': DEFAULT_FIELDS + [
            'locales.access',
            'locales.access_period',
            'height_max',
            'height_min',
            'height_median',
            'routes_quantity',
            'climbing_outdoor_types',
            'rain_proof',
            'children_proof',
            'rock_types',
            'orientations',
            'best_periods',
            'url',
            'climbing_styles',
            'access_time',
            'climbing_rating_max',
            'climbing_rating_min',
            'climbing_rating_median',
            'equipment_ratings'
        ],
        'required': DEFAULT_REQUIRED,
        'listing': DEFAULT_LISTING
    },
    'climbing_indoor': {
        'fields': DEFAULT_FIELDS + [
            'locales.title',
            'locales.summary',
            'locales.description',
            'locales.access',
            'geometry.geom',
            'height_max',
            'height_min',
            'height_median',
            'routes_quantity',
            'climbing_indoor_types',
            'url',
            'phone',
            'climbing_styles',
            'climbing_rating_max',
            'climbing_rating_min',
            'climbing_rating_median'
        ],
        'required': [
            'locales',
            'locales.title',
            'geometry',
            'geometry.geom'
        ],
        'listing': [
            'locales.title',
            'locales.summary',
            'geometry.geom',
            'quality',
            'waypoint_type'
        ]
    },
    'gite': {
        'fields': DEFAULT_FIELDS + [
            'locales.access_period',
            'capacity',
            'capacity_staffed',
            'url',
            'phone',
            'phone_custodian',
            'custodianship'
        ],
        'required': DEFAULT_REQUIRED + [
            'custodianship'
        ],
        'listing': DEFAULT_LISTING
    },
    'camp_site': {
        'fields': DEFAULT_FIELDS + [
            'locales.access_period',
            'capacity',
            'capacity_staffed',
            'url',
            'phone',
            'phone_custodian',
            'custodianship'
        ],
        'required': DEFAULT_REQUIRED + [
            'custodianship'
        ],
        'listing': DEFAULT_LISTING
    },
    'hut': {
        'fields': DEFAULT_FIELDS + [
            'locales.access',
            'locales.access_period',
            'capacity',
            'capacity_staffed',
            'url',
            'phone',
            'phone_custodian',
            'custodianship',
            'matress_unstaffed',
            'blanket_unstaffed',
            'gas_unstaffed',
            'heating_unstaffed',
        ],
        'required': DEFAULT_REQUIRED + [
            'custodianship'
        ],
        'listing': DEFAULT_LISTING
    },
    'shelter': {
        'fields': DEFAULT_FIELDS + [
            'capacity',
            'matress_unstaffed',
            'blanket_unstaffed',
            'gas_unstaffed',
            'heating_unstaffed'
        ],
        'required': DEFAULT_REQUIRED,
        'listing': DEFAULT_LISTING
    },
    'bivouac': {
        'fields': DEFAULT_FIELDS + [
            'capacity',
        ],
        'required': DEFAULT_REQUIRED,
        'listing': DEFAULT_LISTING
    },
    'base_camp': {
        'fields': DEFAULT_FIELDS,
        'required': DEFAULT_REQUIRED,
        'listing': DEFAULT_LISTING
    },
    'access': {
        'fields': DEFAULT_FIELDS + [
            'locales.access',
            'locales.access_period',
            'elevation_min',
            'public_transportation_types',
            'public_transportation_rating',
            'snow_clearance_rating',
            'lift_access',
            'parking_fee'
        ],
        'required': DEFAULT_REQUIRED,
        'listing': DEFAULT_LISTING
    },
    'local_product': {
        'fields': DEFAULT_FIELDS + [
            'locales.access',
            'locales.access_period',
            'product_types',
            'url',
            'phone'
        ],
        'required': DEFAULT_REQUIRED + [
            'product_types'
        ],
        'listing': DEFAULT_LISTING
    },
    'paragliding_takeoff': {
        'fields': DEFAULT_FIELDS + [
            'length',
            'slope',
            'ground_types',
            'paragliding_rating',
            'exposition_rating',
            'orientations'
        ],
        'required': DEFAULT_REQUIRED,
        'listing': DEFAULT_LISTING
    },
    'paragliding_landing': {
        'fields': DEFAULT_FIELDS + [
            'length',
            'slope',
            'ground_types',
            'paragliding_rating',
            'exposition_rating',
            'orientations'
        ],
        'required': DEFAULT_REQUIRED,
        'listing': DEFAULT_LISTING
    },
    'weather_station': {
        'fields': DEFAULT_FIELDS + [
            'weather_station_types',
            'url'
        ],
        'required': DEFAULT_REQUIRED + [
            'url'
        ],
        'listing': DEFAULT_LISTING
    },
    'webcam': {
        'fields': DEFAULT_FIELDS + [
            'url'
        ],
        'required': DEFAULT_REQUIRED + [
            'url'
        ],
        'listing': DEFAULT_LISTING
    },
    'slackline_spot': {
        'fields': DEFAULT_FIELDS + [
            'slackline_types',
            'slackline_length_min',
            'slackline_length_max',
            'locales.access',
            'access_time',
            'best_periods',
            'orientations',
        ],
        'required': DEFAULT_REQUIRED + [
            'slackline_types',
        ],
        'listing': DEFAULT_LISTING + [
            'slackline_types',
            'slackline_length_min',
            'slackline_length_max',
        ]
    }
}
