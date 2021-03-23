DEFAULT_FIELDS = [
    'locales',
    'locales.title',
    'locales.summary',
    'locales.description',
    'locales.place',
    'locales.route_study',
    'locales.conditions',
    'locales.training',
    'locales.motivations',
    'locales.group_management',
    'locales.risk',
    'locales.time_management',
    'locales.safety',
    'locales.reduce_impact',
    'locales.modifications',
    'locales.other_comments',
    'geometry',
    'geometry.geom',
    'elevation',
    'date',
    'event_type',
    'event_activity',
    'nb_participants',
    'nb_impacted',
    'rescue',
    'avalanche_level',
    'avalanche_slope',
    'severity',
    'author_status',
    'activity_rate',
    'age',
    'gender',
    'previous_injuries',
    'autonomy',
    'supervision',
    'qualification',
    'disable_comments',
    'anonymous',
    'quality'
]
DEFAULT_REQUIRED = [
    'locales',
    'locales.title',
    'geometry.geom'
]
DEFAULT_LISTING = [
    'locales',
    'locales.title',
    'geometry',
    'geometry.geom',
    'elevation',
    'date',
    'event_type',
    'event_activity',
    'nb_participants',
    'nb_impacted',
    'avalanche_level',
    'avalanche_slope',
    'severity',
    'quality'
]

fields_xreport = {
    'fields': DEFAULT_FIELDS,
    'required': DEFAULT_REQUIRED,
    'listing': DEFAULT_LISTING
}
