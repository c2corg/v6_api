# Common attributes settings used by most outing activities
DEFAULT_FIELDS = [
    'locales.title',
    'locales.summary',
    'locales.description',
    'locales.participants',
    'locales.access_comment',
    'locales.weather',
    'locales.timing',
    'locales.conditions_levels',
    'locales.conditions',
    'locales.hut_comment',
    'locales.route_description',
    'geometry.geom',
    'geometry.geom_detail',
    'activities',
    'date_start',
    'date_end',
    'frequentation',
    'participant_count',
    'elevation_min',
    'elevation_max',
    'elevation_access',
    'height_diff_up',
    'height_diff_down',
    'length_total',
    'partial_trip',
    'public_transport',
    'access_condition',
    'lift_status',
    'condition_rating',
    'hut_status',
    'disable_comments',
    'quality'
]
DEFAULT_REQUIRED = [
    'locales',
    'locales.title',
    'activities',
    'date_start',
    'date_end'
]
DEFAULT_LISTING = [
    'locales.title',
    'locales.summary',
    'geometry.geom',
    'geometry.has_geom_detail',
    'activities',
    'date_start',
    'date_end',
    'elevation_max',
    'height_diff_up',
    'public_transport',
    'condition_rating',
    'quality',
    'version_date'
]
DEFAULT_ATTRIBUTES_SETTINGS = {
    'fields': DEFAULT_FIELDS,
    'required': DEFAULT_REQUIRED,
    'listing': DEFAULT_LISTING
}

fields_outing = {
    'skitouring': {
        'fields': DEFAULT_FIELDS + [
            'elevation_up_snow',
            'elevation_down_snow',
            'snow_quantity',
            'snow_quality',
            'glacier_rating',
            'avalanche_signs',
            'locales.avalanches',
            'ski_rating',
            'labande_global_rating'
        ],
        'required': DEFAULT_REQUIRED,
        'listing': DEFAULT_LISTING + [
            'ski_rating',
            'labande_global_rating'
        ]
    },
    'snow_ice_mixed': {
        'fields': DEFAULT_FIELDS + [
            'elevation_up_snow',
            'elevation_down_snow',
            'snow_quantity',
            'snow_quality',
            'glacier_rating',
            'avalanche_signs',
            'locales.avalanches',
            'height_diff_difficulties',
            'global_rating',
            'engagement_rating'
        ],
        'required': DEFAULT_REQUIRED,
        'listing': DEFAULT_LISTING + [
            'height_diff_difficulties',
            'global_rating',
            'engagement_rating'
        ]
    },
    'mountain_climbing': {
        'fields': DEFAULT_FIELDS + [
            'elevation_up_snow',
            'elevation_down_snow',
            'snow_quantity',
            'snow_quality',
            'glacier_rating',
            'global_rating',
            'engagement_rating',
            'height_diff_difficulties'
        ],
        'required': DEFAULT_REQUIRED,
        'listing': DEFAULT_LISTING + [
            'global_rating',
            'engagement_rating',
            'height_diff_difficulties'
        ]
    },
    'rock_climbing': {
        'fields': DEFAULT_FIELDS + [
            'global_rating',
            'equipment_rating',
            'rock_free_rating'
        ],
        'required': DEFAULT_REQUIRED,
        'listing': DEFAULT_LISTING + [
            'global_rating',
            'equipment_rating',
            'rock_free_rating'
        ]
    },
    'ice_climbing': {
        'fields': DEFAULT_FIELDS + [
            'elevation_up_snow',
            'elevation_down_snow',
            'snow_quantity',
            'snow_quality',
            'avalanche_signs',
            'locales.avalanches',
            'global_rating',
            'ice_rating'
        ],
        'required': DEFAULT_REQUIRED,
        'listing': DEFAULT_LISTING + [
            'global_rating',
            'ice_rating'
        ]
    },
    'hiking': {
        'fields': DEFAULT_FIELDS + [
            'hiking_rating'
        ],
        'required': DEFAULT_REQUIRED,
        'listing': DEFAULT_LISTING + [
            'hiking_rating'
        ]
    },
    'snowshoeing': {
        'fields': DEFAULT_FIELDS + [
            'elevation_up_snow',
            'elevation_down_snow',
            'snow_quantity',
            'snow_quality',
            'glacier_rating',
            'avalanche_signs',
            'locales.avalanches',
            'snowshoe_rating'
        ],
        'required': DEFAULT_REQUIRED,
        'listing': DEFAULT_LISTING + [
            'snowshoe_rating'
        ]
    },
    'mountain_biking': {
        'fields': DEFAULT_FIELDS + [
            'mtb_up_rating',
            'mtb_down_rating'
        ],
        'required': DEFAULT_REQUIRED,
        'listing': DEFAULT_LISTING + [
            'mtb_up_rating',
            'mtb_down_rating'
        ]
    },
    'via_ferrata': {
        'fields': DEFAULT_FIELDS + [
            'via_ferrata_rating'
        ],
        'required': DEFAULT_REQUIRED,
        'listing': DEFAULT_LISTING + [
            'via_ferrata_rating'
        ]
    },
    'paragliding': {
        'fields': DEFAULT_FIELDS + [
        ],
        'required': DEFAULT_REQUIRED,
        'listing': DEFAULT_LISTING
    },
    'slacklining': {
        'fields': DEFAULT_FIELDS,
        'required': DEFAULT_REQUIRED,
        'listing': DEFAULT_LISTING
    },
}
