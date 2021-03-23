DEFAULT_FIELDS = [
    'locales.title',
    'geometry.geom_detail',
    'code',
    'scale',
    'editor'
]

DEFAULT_REQUIRED = [
    'locales',
    'locales.title',
    'geometry',
    'geometry.geom_detail'
]

LISTING_FIELDS = [
    'locales.title',
    'code',
    'editor'
]

fields_topo_map = {
    'fields': DEFAULT_FIELDS,
    'required': DEFAULT_REQUIRED,
    'listing': LISTING_FIELDS
}
