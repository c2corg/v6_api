DEFAULT_FIELDS = [
    'locales.title',
    'locales.summary',
    'locales.description',
    'locales.lang',
    'activities',
    'categories',
    'quality',
    'article_type'
]

DEFAULT_REQUIRED = [
    'locales',
    'locales.title',
    'article_type'
]

LISTING_FIELDS = [
    'locales',
    'locales.title',
    'locales.summary',
    'categories',
    'activities',
    'quality',
    'article_type'
]

fields_article = {
    'fields': DEFAULT_FIELDS,
    'required': DEFAULT_REQUIRED,
    'listing': LISTING_FIELDS
}
