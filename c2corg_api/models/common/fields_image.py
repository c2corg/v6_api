DEFAULT_FIELDS = [
    'locales.title',
    'locales.summary',
    'locales.description',
    'geometry.geom',
    'activities',
    'categories',
    'image_type',
    'author',
    'elevation',
    'height',
    'width',
    'file_size',
    'filename',
    'camera_name',
    'exposure_time',
    'focal_length',
    'fnumber',
    'iso_speed',
    'quality',
]

DEFAULT_REQUIRED = ['locales', 'image_type']

# width and height of the original image: the UI keeps the space of the
# thumbnails while they load (galleries, associations). The time of the shot
# and the camera: the UI locates the images of an outing on its GPS track
# without reading each image (c2corg/c2c_ui#4259)
LISTING_FIELDS = [
    'locales.title',
    'geometry.geom',
    'filename',
    'author',
    'image_type',
    'width',
    'height',
    'date_time',
    'camera_name',
]

fields_image = {
    'fields': DEFAULT_FIELDS,
    'required': DEFAULT_REQUIRED,
    'listing': LISTING_FIELDS,
}
