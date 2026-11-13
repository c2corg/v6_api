"""The documents of the contract tests, created through the API."""

from dataclasses import dataclass
from unittest.mock import Mock, patch

POINT = '{"type": "Point", "coordinates": [635956, 5723604]}'
LINE = '{"type": "LineString", "coordinates": [[635956, 5723604], [635966, 5723644]]}'
POLYGON = (
    '{"type": "Polygon", "coordinates": [[[635000, 5723000], [635000, 5724000], '
    '[637000, 5724000], [637000, 5723000], [635000, 5723000]]]}'
)

# only moderators may change these
MODERATED_TYPES = ('areas', 'maps')
# what a GET returns but a POST or PUT does not take
READ_ONLY_FIELDS = ('areas', 'maps', 'available_langs', 'cooked')


def writable(document, keep_ids=True):
    """Turn a document as GET returns it into a POST or PUT body."""
    for field in READ_ONLY_FIELDS:
        document.pop(field, None)
    if not keep_ids:
        document.pop('document_id', None)
        document.pop('version', None)
    # GET returns the associated documents, a write takes their ids
    associations = document.pop('associations', None) or {}
    document['associations'] = {
        kind: [{'document_id': d['document_id']} for d in docs]
        for kind, docs in associations.items()
        if isinstance(docs, list)
    }
    return document


@dataclass
class Documents:
    """One document of each type, by URL prefix, and how to change them."""

    browser: object
    ids: dict

    def url(self, prefix, path=''):
        return f'/{prefix}/{self.ids[prefix]}{path}'

    def update(self, prefix, change, user='contributor', status=200):
        """Change a document through the API and return the response."""
        document = writable(self.browser.get(self.url(prefix), user=user).json)
        change(document)
        body = {'message': 'contract test', 'document': document}
        return self.browser.put(self.url(prefix), body, user=user, status=status)

    def history(self, prefix, lang='en'):
        """Return the version ids of a document, oldest first."""
        versions = self.browser.get(f'/document/{self.ids[prefix]}/history/{lang}').json
        return sorted(v['version_id'] for v in versions['versions'])

    def retitle(self, prefix):
        """Change the title of a document (the description of a profile)."""

        def change(document):
            # profiles have no title
            field = 'description' if prefix == 'profiles' else 'title'
            locale = document['locales'][0]
            locale[field] = (locale.get(field) or '') + ' (2)'

        user = 'moderator' if prefix in MODERATED_TYPES else 'contributor'
        return self.update(prefix, change, user=user)


def create_documents(browser, user_ids):
    """Create one document of each type through the API."""
    ids = {'profiles': user_ids['contributor']}
    ids['waypoints'] = browser.create(
        'waypoints',
        {
            'waypoint_type': 'summit',
            'elevation': 3779,
            'geometry': {'geom': POINT},
            'locales': [{'lang': 'en', 'title': 'Mont Pourri', 'access': 'y'}],
        },
    )
    waypoint = [{'document_id': ids['waypoints']}]
    ids['routes'] = browser.create(
        'routes',
        {
            'main_waypoint_id': ids['waypoints'],
            'activities': ['hiking'],
            'elevation_min': 700,
            'elevation_max': 1500,
            'height_diff_up': 800,
            'height_diff_down': 800,
            'durations': ['1'],
            'geometry': {'geom_detail': LINE},
            'locales': [{'lang': 'en', 'title': 'Some nice loop', 'gear': 'shoes'}],
            'associations': {'waypoints': waypoint},
        },
    )
    ids['outings'] = browser.create(
        'outings',
        {
            'activities': ['hiking'],
            'date_start': '2016-01-01',
            'date_end': '2016-01-02',
            'elevation_max': 1500,
            'geometry': {'geom_detail': LINE},
            'locales': [{'lang': 'en', 'title': 'A nice day', 'weather': 'sunny'}],
            'associations': {
                'users': [{'document_id': user_ids['contributor']}],
                'routes': [{'document_id': ids['routes']}],
            },
        },
    )
    ids['articles'] = browser.create(
        'articles',
        {
            'categories': ['site_info'],
            'activities': ['hiking'],
            'article_type': 'collab',
            'locales': [{'lang': 'en', 'title': "Lac d'Annecy"}],
            'associations': {'waypoints': waypoint},
        },
    )
    ids['books'] = browser.create(
        'books',
        {
            'activities': ['hiking'],
            'book_types': ['biography'],
            'author': 'Author',
            'locales': [{'lang': 'en', 'title': 'Escalades au Thaurac'}],
            'associations': {'waypoints': waypoint},
        },
    )
    with patch(
        'c2corg_api.views.image.requests.post', return_value=Mock(status_code=200)
    ):
        ids['images'] = browser.create(
            'images',
            {
                'filename': 'image.jpg',
                'activities': ['hiking'],
                'image_type': 'collaborative',
                'height': 1500,
                'geometry': {'geom': POINT},
                'locales': [{'lang': 'en', 'title': 'A view'}],
                'associations': {'waypoints': waypoint},
            },
        )
    ids['xreports'] = browser.create(
        'xreports',
        {
            'event_activity': 'skitouring',
            'event_type': 'stone_ice_fall',
            'nb_participants': 5,
            'geometry': {'geom': POINT},
            'locales': [{'lang': 'en', 'title': 'Stone fall'}],
        },
    )
    ids['areas'] = browser.create(
        'areas',
        {
            'area_type': 'range',
            'geometry': {'geom_detail': POLYGON},
            'locales': [{'lang': 'en', 'title': 'Chartreuse'}],
        },
        user='moderator',
    )
    ids['maps'] = browser.create(
        'maps',
        {
            'editor': 'IGN',
            'scale': '25000',
            'code': '3432OT',
            'geometry': {'geom_detail': POLYGON},
            'locales': [{'lang': 'en', 'title': 'Annecy'}],
        },
        user='moderator',
    )
    ids['coverages'] = browser.create(
        'coverages',
        {
            'coverage_type': 'fr-se',
            'geometry': {'geom_detail': POLYGON},
            'locales': [{'lang': 'en', 'title': 'Coverage'}],
        },
    )
    return Documents(browser, ids)
