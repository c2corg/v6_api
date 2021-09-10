DEFAULT_FIELDS = [
    'locales.title',
    'geometry.geom_detail',
    'area_type',
    'quality',
    'fundraiser_url'
]

DEFAULT_REQUIRED = [
    'locales',
    'locales.title',
    'geometry',
    'geometry.geom_detail',
    'area_type'
]

LISTING_FIELDS = [
    'locales.title',
    'area_type',
    'fundraiser_url'
]

fields_area = {
    'fields': DEFAULT_FIELDS,
    'required': DEFAULT_REQUIRED,
    'listing': LISTING_FIELDS
}
