"""The outings of the partner sites, merged with those of c2c."""
# `GET /partner-outings` lists the rows of guidebook.partner_outings (harvested)
# and the outings of the topoguide (read at query time, never copied) in one
# `UNION ALL`, so that the order, the paging and the total are those of the
# union. The SQL is plain PostgreSQL 9.6 (`array_position` is from 9.5).
# Every value reaches the SQL as a bound parameter, array literals included
# (`'{1,2}'` cast by the query): the filters are validated first.

import datetime
import json
import math

from sqlalchemy import text

from c2corg_api import caching
from c2corg_api.caching import cache_partner_outings, get_or_create
from c2corg_api.models.common import attributes
from c2corg_api.partners.sources import SOURCE_NAMES

C2C = 'c2c'

# name, url and credit of the sites
SITES = {
    C2C: ('camptocamp.org', 'https://www.camptocamp.org'),
    'skitour': ('skitour.fr', 'https://skitour.fr'),
    'gulliver': ('gulliver.it', 'https://www.gulliver.it'),
}

# the window of the listing, in days, when `date` is not given; the longest
# window a request may ask for
DEFAULT_DAYS = 14
MAX_SPAN_DAYS = 31

DEFAULT_LIMIT = 100
MAX_LIMIT = 300

CACHE_EXPIRATION = 120

# steep skiing: a ski rating from 4.1, or a global rating (Labande) from D-
STEEP_SKI_RATINGS = attributes.ski_ratings[attributes.ski_ratings.index('4.1') :]
STEEP_GLOBAL_RATINGS = attributes.global_ratings[
    attributes.global_ratings.index('D-') :
]

_TRUE = ('true', '1')
_FALSE = ('false', '0')


class InvalidParam(Exception):
    """A query parameter is not valid: the name of the parameter."""

    def __init__(self, name):
        super().__init__(name)
        self.name = name


def today():
    """Return the day the default window ends on (a function: tests set it)."""
    return datetime.datetime.now(datetime.UTC).date()


# parameters


def _tokens(name, value):
    tokens = [token.strip() for token in value.split(',')]
    if not all(tokens):
        raise InvalidParam(name)
    return tokens


def _a(value):
    try:
        ids = sorted({int(token) for token in _tokens('a', value)})
    except ValueError:
        raise InvalidParam('a') from None
    if any(i < 0 for i in ids):
        raise InvalidParam('a')
    return ids


def _bbox(value):
    tokens = _tokens('bbox', value)
    try:
        bbox = [float(token) for token in tokens]
    except ValueError:
        raise InvalidParam('bbox') from None
    if len(bbox) != 4 or not all(math.isfinite(v) for v in bbox):
        raise InvalidParam('bbox')
    xmin, ymin, xmax, ymax = bbox
    if xmin > xmax or ymin > ymax:
        raise InvalidParam('bbox')
    return bbox


def _day(value):
    try:
        return datetime.date.fromisoformat(value.strip())
    except ValueError:
        raise InvalidParam('date') from None


def _date(value):
    parts = value.split(',')
    if len(parts) > 2:
        raise InvalidParam('date')
    start = _day(parts[0])
    end = _day(parts[1]) if len(parts) == 2 else start
    if end < start or (end - start).days > MAX_SPAN_DAYS:
        raise InvalidParam('date')
    return start, end


def _act(value):
    activities = sorted(set(_tokens('act', value)))
    if not set(activities) <= set(attributes.activities):
        raise InvalidParam('act')
    return activities


def _trat(value):
    parts = [part.strip() for part in value.split(',')]
    if len(parts) != 2 or not any(parts):
        raise InvalidParam('trat')
    if any(part and part not in attributes.ski_ratings for part in parts):
        raise InvalidParam('trat')
    low, high = parts
    ratings = attributes.ski_ratings
    if low and high and ratings.index(low) > ratings.index(high):
        raise InvalidParam('trat')
    return low or None, high or None


def _steep(value):
    value = value.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise InvalidParam('steep')


def _sources(value):
    sources = sorted(set(_tokens('sources', value)))
    if not set(sources) <= {*SOURCE_NAMES, C2C}:
        raise InvalidParam('sources')
    return sources


def _lang(value):
    if value not in attributes.default_langs:
        raise InvalidParam('pl')
    return value


def _limit(value):
    try:
        limit = int(value)
    except ValueError:
        raise InvalidParam('limit') from None
    if not 1 <= limit <= MAX_LIMIT:
        raise InvalidParam('limit')
    return limit


def _offset(value):
    try:
        offset = int(value)
    except ValueError:
        raise InvalidParam('offset') from None
    if offset < 0:
        raise InvalidParam('offset')
    return offset


_PARSERS = {
    'a': _a,
    'bbox': _bbox,
    'date': _date,
    'act': _act,
    'trat': _trat,
    'steep': _steep,
    'sources': _sources,
    'pl': _lang,
    'limit': _limit,
    'offset': _offset,
}


def parse_params(raw):
    """Return the normalised parameters of a listing, or raise `InvalidParam`.

    `raw` maps the names to the strings of the query (or None, or empty, for
    the parameters not given). The result has every key: None when a filter
    is not given.
    """
    params = {}
    for name, parse in _PARSERS.items():
        value = raw.get(name)
        params[name] = parse(value) if value not in (None, '') else None
    if params['date'] is None:
        end = today()
        params['date'] = (end - datetime.timedelta(days=DEFAULT_DAYS - 1), end)
    if params['limit'] is None:
        params['limit'] = DEFAULT_LIMIT
    if params['offset'] is None:
        params['offset'] = 0
    return params


def cache_key(params):
    """Return the cache key of a listing: the cache version, the parameters."""
    return '{}-{}'.format(
        caching.CACHE_VERSION,
        json.dumps(params, sort_keys=True, default=str, separators=(',', ':')),
    )


# SQL


def _array(values):
    # an array literal, for a bound parameter cast by the query
    return '{' + ','.join(str(v) for v in values) + '}'


def _partner_side(params, binds):
    where = ['p.date BETWEEN :start AND :end']
    if params['a']:
        binds['a'] = _array(params['a'])
        where.append('p.area_ids && CAST(:a AS integer[])')
    if params['bbox']:
        where.append('p.geom && ST_MakeEnvelope(:xmin, :ymin, :xmax, :ymax, 3857)')
    if params['act']:
        where.append('p.activities && CAST(:act AS guidebook.activity_type[])')
    if params['trat']:
        low, high = params['trat']
        ratings = attributes.ski_ratings
        # the intervals overlap: min <= qmax and max >= qmin. The comparisons
        # use lists of ratings, never the order of the enum. A NULL (no
        # rating) matches no list: such rows are left out.
        if high:
            binds['trat_below'] = _array(ratings[: ratings.index(high) + 1])
            where.append(
                'p.ski_rating_min = ANY(CAST(:trat_below AS guidebook.ski_rating[]))'
            )
        if low:
            binds['trat_above'] = _array(ratings[ratings.index(low) :])
            where.append(
                'p.ski_rating_max = ANY(CAST(:trat_above AS guidebook.ski_rating[]))'
            )
    if params['steep'] is not None:
        binds['steep'] = params['steep']
        where.append('p.steep = :steep')
    if params['sources']:
        partners = [s for s in params['sources'] if s != C2C]
        binds['sources'] = _array(partners)
        where.append('p.source = ANY(CAST(:sources AS text[]))')
    return f"""
        SELECT p.source AS source, p.id AS row_id,
               p.external_id AS external_id, NULL::integer AS document_id,
               p.url AS url, p.title AS title, p.lang::text AS lang,
               p.date AS date, p.author AS author,
               p.author_url AS author_url,
               p.activities::text[] AS activities,
               p.source_activity AS source_activity,
               p.ski_rating_min::text AS ski_rating_min,
               p.ski_rating_max::text AS ski_rating_max,
               p.rating_raw AS rating_raw, p.rating_system AS rating_system,
               p.steep AS steep, p.elevation_max::integer AS elevation_max,
               p.height_diff_up::integer AS height_diff_up,
               p.orientations::text[] AS orientations, p.snow AS snow,
               p.region AS region, p.geom AS geom,
               p.geom_quality AS geom_quality, p.area_ids AS area_ids
        FROM guidebook.partner_outings p
        WHERE {' AND '.join(where)}"""


def _c2c_side(params, binds):
    where = ['d.redirects_to IS NULL', "d.quality <> 'empty'"]
    where.append('o.date_end BETWEEN :start AND :end')
    if params['a']:
        binds['a'] = _array(params['a'])
        where.append(
            'EXISTS (SELECT 1 FROM guidebook.area_associations aa'
            ' WHERE aa.document_id = o.document_id'
            ' AND aa.area_id = ANY(CAST(:a AS integer[])))'
        )
    if params['bbox']:
        where.append('g.geom && ST_MakeEnvelope(:xmin, :ymin, :xmax, :ymax, 3857)')
    if params['act']:
        where.append('o.activities && CAST(:act AS guidebook.activity_type[])')
    if params['trat']:
        low, high = params['trat']
        ratings = attributes.ski_ratings
        first = ratings.index(low) if low else 0
        last = ratings.index(high) if high else len(ratings) - 1
        binds['trat'] = _array(ratings[first : last + 1])
        where.append('o.ski_rating = ANY(CAST(:trat AS guidebook.ski_rating[]))')
    binds['steep_ski'] = _array(STEEP_SKI_RATINGS)
    binds['steep_global'] = _array(STEEP_GLOBAL_RATINGS)
    steep = (
        'COALESCE(o.ski_rating = ANY(CAST(:steep_ski AS guidebook.ski_rating[]))'
        ' OR o.labande_global_rating'
        ' = ANY(CAST(:steep_global AS guidebook.global_rating[])), false)'
    )
    if params['steep'] is not None:
        where.append(steep if params['steep'] else f'NOT {steep}')
    # the c2c outings have no url (the UI routes to the outing); their title,
    # author and areas are read for the page only
    return f"""
        SELECT 'c2c'::text AS source, o.document_id AS row_id,
               o.document_id::text AS external_id,
               o.document_id AS document_id, NULL::text AS url,
               NULL::text AS title, NULL::text AS lang,
               o.date_end AS date, NULL::text AS author,
               NULL::text AS author_url, o.activities::text[] AS activities,
               NULL::text AS source_activity,
               o.ski_rating::text AS ski_rating_min,
               o.ski_rating::text AS ski_rating_max,
               o.ski_rating::text AS rating_raw,
               CASE WHEN o.ski_rating IS NOT NULL THEN 'c2c_ski' END
                   AS rating_system,
               {steep} AS steep, o.elevation_max::integer AS elevation_max,
               o.height_diff_up::integer AS height_diff_up,
               NULL::text[] AS orientations, NULL::jsonb AS snow,
               NULL::text AS region, g.geom AS geom,
               CASE WHEN g.geom IS NOT NULL THEN 'start' ELSE 'none' END
                   AS geom_quality, NULL::integer[] AS area_ids
        FROM guidebook.outings o
        JOIN guidebook.documents d ON d.document_id = o.document_id
        LEFT JOIN guidebook.documents_geometries g
            ON g.document_id = o.document_id
        WHERE {' AND '.join(where)}"""


def _union(params, binds):
    start, end = params['date']
    binds.update(start=start, end=end)
    if params['bbox']:
        binds.update(zip(('xmin', 'ymin', 'xmax', 'ymax'), params['bbox'], strict=True))
    if params['act']:
        binds['act'] = _array(params['act'])
    sources = params['sources']
    sides = []
    if sources is None or any(s != C2C for s in sources):
        sides.append(_partner_side(params, binds))
    if sources is None or C2C in sources:
        sides.append(_c2c_side(params, binds))
    return ' UNION ALL '.join(f'({side})' for side in sides)


_ORDER = 'date DESC, source, row_id'


def _query_page(session, params):
    binds = {}
    union = _union(params, binds)
    total = session.execute(
        text(f'SELECT count(*) FROM ({union}) u'), binds
    ).scalar_one()
    binds.update(limit=params['limit'], offset=params['offset'])
    rows = session.execute(
        text(
            f"""
            SELECT page.*, ST_AsGeoJSON(page.geom, 1, 0) AS geojson
            FROM (SELECT * FROM ({union}) u ORDER BY {_ORDER}
                  LIMIT :limit OFFSET :offset) page
            ORDER BY {_ORDER}"""
        ),
        binds,
    ).mappings()
    return total, [dict(row) for row in rows]


def _lang_priority(pl):
    langs = [pl] if pl else []
    return _array(langs + attributes.langs_priority)


def _best_locales(session, document_ids, pl):
    """Return {document_id: (lang, title)}: `pl` first, then the usual order."""
    if not document_ids:
        return {}
    rows = session.execute(
        text(
            """
            SELECT DISTINCT ON (l.document_id) l.document_id, l.lang, l.title
            FROM guidebook.documents_locales l
            WHERE l.document_id = ANY(CAST(:ids AS integer[]))
            ORDER BY l.document_id,
                     array_position(CAST(:priority AS text[]), l.lang::text)
                         NULLS LAST,
                     l.lang"""
        ),
        {'ids': _array(document_ids), 'priority': _lang_priority(pl)},
    )
    return {row.document_id: (row.lang, row.title) for row in rows}


def _authors(session, document_ids):
    """Return {outing id: name} of the first user associated to each outing."""
    if not document_ids:
        return {}
    rows = session.execute(
        text(
            """
            SELECT DISTINCT ON (a.child_document_id)
                   a.child_document_id AS outing_id, u.name
            FROM guidebook.associations a
            JOIN users."user" u ON u.id = a.parent_document_id
            WHERE a.parent_document_type = 'u'
              AND a.child_document_type = 'o'
              AND a.child_document_id = ANY(CAST(:ids AS integer[]))
            ORDER BY a.child_document_id, a.parent_document_id"""
        ),
        {'ids': _array(document_ids)},
    )
    return {row.outing_id: row.name for row in rows}


def _outing_areas(session, document_ids):
    """Return {outing id: [area ids]} from the associations of the areas."""
    if not document_ids:
        return {}
    rows = session.execute(
        text(
            """
            SELECT aa.document_id, aa.area_id
            FROM guidebook.area_associations aa
            WHERE aa.document_id = ANY(CAST(:ids AS integer[]))"""
        ),
        {'ids': _array(document_ids)},
    )
    areas = {}
    for row in rows:
        areas.setdefault(row.document_id, []).append(row.area_id)
    return areas


def _area_titles(session, area_ids, pl):
    """Return {area id: {document_id, area_type, title}} in the best locale."""
    if not area_ids:
        return {}
    rows = session.execute(
        text(
            """
            SELECT DISTINCT ON (a.document_id)
                   a.document_id, a.area_type::text AS area_type, l.title
            FROM guidebook.areas a
            JOIN guidebook.documents d ON d.document_id = a.document_id
            JOIN guidebook.documents_locales l
                ON l.document_id = a.document_id
            WHERE a.document_id = ANY(CAST(:ids AS integer[]))
              AND d.redirects_to IS NULL
            ORDER BY a.document_id,
                     array_position(CAST(:priority AS text[]), l.lang::text)
                         NULLS LAST,
                     l.lang"""
        ),
        {'ids': _array(sorted(area_ids)), 'priority': _lang_priority(pl)},
    )
    return {
        row.document_id: {
            'document_id': row.document_id,
            'area_type': row.area_type,
            'title': row.title,
        }
        for row in rows
    }


# serialisation


def _credit(source):
    site, url = SITES.get(source, (source, ''))
    return {'site': site, 'site_url': url}


def _rating(row):
    rating = {
        'ski_rating_min': row['ski_rating_min'],
        'ski_rating_max': row['ski_rating_max'],
        'raw': row['rating_raw'],
        'system': row['rating_system'],
    }
    return rating if any(v is not None for v in rating.values()) else None


def _author(name, url):
    return {'name': name, 'url': url} if name or url else None


def _item(row, locales, authors, areas, titles):
    c2c = row['source'] == C2C
    document_id = row['document_id']
    if c2c:
        lang, title = locales.get(document_id, (None, ''))
        author = _author(authors.get(document_id), None)
        area_ids = areas.get(document_id, [])
    else:
        lang, title = row['lang'], row['title']
        author = _author(row['author'], row['author_url'])
        area_ids = row['area_ids'] or []
    geometry = None
    if row['geojson']:
        geometry = {'geom': row['geojson'], 'quality': row['geom_quality']}
    return {
        'id': f'{row["source"]}:{row["external_id"]}',
        'source': row['source'],
        'document_id': document_id,
        'url': row['url'],
        'title': title,
        'lang': lang,
        'date': row['date'].isoformat(),
        'author': author,
        'activities': row['activities'],
        'source_activity': row['source_activity'],
        'rating': _rating(row),
        'steep': row['steep'],
        'elevation_max': row['elevation_max'],
        'height_diff_up': row['height_diff_up'],
        'orientations': row['orientations'] or [],
        'snow': row['snow'],
        'region': row['region'],
        'geometry': geometry,
        'areas': [titles[i] for i in sorted(area_ids) if i in titles],
        'credit': _credit(row['source']),
    }


def _iso(value):
    return value.isoformat() if value else None


def read_sources(session):
    """Return the health of the sources, as the listing and /sources give it."""
    rows = session.execute(
        text(
            """
            SELECT source, status, status_detail, last_success_at,
                   last_run_at, last_fetched, last_skipped
            FROM guidebook.partner_sources ORDER BY source"""
        )
    ).mappings()
    sources = {row['source']: row for row in rows}
    result = []
    # a source that never ran has no row yet: it is listed all the same
    for name in sorted({*sources, *SOURCE_NAMES}):
        row = sources.get(name)
        site, url = SITES.get(name, (name, ''))
        result.append(
            {
                'source': name,
                'site_name': site,
                'site_url': url,
                'status': row['status'] if row else 'never_run',
                'status_detail': row['status_detail'] if row else None,
                'last_success_at': _iso(row['last_success_at']) if row else None,
                'last_run_at': _iso(row['last_run_at']) if row else None,
                'last_fetched': row['last_fetched'] if row else None,
                'last_skipped': (row['last_skipped'] or {}) if row else {},
            }
        )
    return result


def _list(session, params):
    total, rows = _query_page(session, params)
    pl = params['pl']
    c2c_ids = [r['document_id'] for r in rows if r['source'] == C2C]
    locales = _best_locales(session, c2c_ids, pl)
    authors = _authors(session, c2c_ids)
    areas = _outing_areas(session, c2c_ids)
    area_ids = {i for ids in areas.values() for i in ids}
    area_ids.update(i for r in rows for i in r['area_ids'] or [])
    titles = _area_titles(session, area_ids, pl)
    return {
        'total': total,
        'items': [_item(row, locales, authors, areas, titles) for row in rows],
        # the health of the sources, the status of the listing at a glance
        'sources': [
            {
                'source': s['source'],
                'status': s['status'],
                'last_success_at': s['last_success_at'],
            }
            for s in read_sources(session)
        ],
    }


def list_partner_outings(session, params):
    """Return {total, items, sources}, cached for two minutes."""
    return get_or_create(
        cache_partner_outings,
        cache_key(params),
        lambda: _list(session, params),
        expiration_time=CACHE_EXPIRATION,
    )


def list_sources(session):
    """Return {sources}: the health rows, never the cursor nor a secret."""
    return {'sources': read_sources(session)}
