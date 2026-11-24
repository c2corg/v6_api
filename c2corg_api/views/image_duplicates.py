"""The duplicate images: the same file uploaded twice, listed for the moderators."""

# The same photo is often uploaded twice: as a personal image of an outing and
# as a collaborative image of a route, or twice to the same document. The
# copies are the same file: the same size, dimensions and EXIF date. The size
# and dimensions alone are not enough: with hundreds of thousands of images,
# different photos often have the same size (9 of 14k such sets in 2018 had
# different EXIF dates). No hash of the files is stored.
#
# The sets are computed from all the images (1 s for 650k images, a scan
# of the whole table): the result is cached for an hour, the query runs at
# most once an hour whatever the moderators click. Each request then checks
# the images of the cached sets (by id): merged or deleted images, and
# dismissed pairs, leave the list at once; new copies show within an hour.
# A moderator merges the copies (POST /documents/merge), deletes one, or
# dismisses the set: the pairs are kept in DismissedImageDuplicate, a set is
# hidden while all its pairs are dismissed.

from itertools import combinations

from sqlalchemy import Integer, bindparam, func, select, text
from sqlalchemy.dialects.postgresql import ARRAY, insert

from c2corg_api import caching
from c2corg_api.caching import cache_image_duplicates, get_or_create
from c2corg_api.models import DBSession
from c2corg_api.models.association import Association
from c2corg_api.models.document import Document
from c2corg_api.models.image import Image
from c2corg_api.models.image_duplicate import DismissedImageDuplicate
from c2corg_api.models.image_embed import ImageEmbed
from c2corg_api.schemas.base import Schema, body_validator
from c2corg_api.schemas.types import Int, Seq
from c2corg_api.views.document_trash import _user, _users
from c2corg_api.views.image_orphans import _created, _iso, _titles
from c2corg_api.views.resource import write

LIMIT_DEFAULT = 30
LIMIT_MAX = 100
# the images of one dismissal
DISMISS_MAX = 100
# the images without EXIF date uploaded by different users are copies only
# when uploaded within this time (photos shared after a group outing)
NO_EXIF_SPAN = '7 days'
# how long the sets are cached (seconds)
SETS_EXPIRATION = 3600
# the query gives up past this time rather than load the database
SETS_TIMEOUT = '20s'

# The sets, the last uploaded first. GROUP BY puts the images without EXIF
# date together: the size and dimensions alone often match by chance, such a
# set is kept when one user uploaded all its images, or within NO_EXIF_SPAN
# (the first versions tell who and when). The images merged into another
# (redirected) are left out after the grouping: joining the documents first
# takes seconds. `same_document`: two of the images are linked to the same
# document, when computed (an image merged since may change it).
SETS_QUERY = """
WITH candidates AS (
  SELECT array_agg(document_id) AS ids, date_time
  FROM guidebook.images
  WHERE file_size IS NOT NULL
  GROUP BY file_size, width, height, date_time
  HAVING count(*) > 1
), sets AS (
  SELECT array_agg(d.document_id ORDER BY d.document_id) AS ids,
         max(d.document_id) AS newest, c.date_time
  FROM candidates c
  CROSS JOIN LATERAL unnest(c.ids) AS u (id)
  JOIN guidebook.documents d ON d.document_id = u.id
  WHERE d.redirects_to IS NULL
  GROUP BY c.ids, c.date_time
  HAVING count(*) > 1
), uploads AS (
  SELECT s.ids,
         count(DISTINCT first.user_id) AS uploaders,
         max(first.written_at) - min(first.written_at) AS span
  FROM sets s
  CROSS JOIN LATERAL unnest(s.ids) AS u (id)
  CROSS JOIN LATERAL (
    SELECT h.user_id, h.written_at
    FROM guidebook.documents_versions v
    JOIN guidebook.history_metadata h ON h.id = v.history_metadata_id
    WHERE v.document_id = u.id
    ORDER BY h.id
    LIMIT 1
  ) first
  WHERE s.date_time IS NULL
  GROUP BY s.ids
)
SELECT s.ids,
  EXISTS (
    SELECT 1
    FROM guidebook.associations a1
    JOIN guidebook.associations a2
      ON a2.parent_document_id = a1.parent_document_id
     AND a2.child_document_id > a1.child_document_id
    WHERE a1.child_document_id = ANY (s.ids)
      AND a2.child_document_id = ANY (s.ids)
  ) AS same_document
FROM sets s
LEFT JOIN uploads up ON up.ids = s.ids
WHERE (
  s.date_time IS NOT NULL
  OR up.uploaders = 1
  OR up.span <= interval '{no_exif_span}'
)
ORDER BY s.newest DESC
"""


def list_duplicate_images(offset, limit, same_document=False):
    """Return the sets of duplicate images, the last uploaded first."""
    shown = _shown(_sets(), same_document)
    rows = shown[offset : offset + limit]
    ids = [image_id for image_ids, _ in rows for image_id in image_ids]
    images = _images(ids)
    created = _created(ids)
    links = _links(ids)
    embeds = _embeds(ids)
    users = _users([user_id for _, user_id in created.values()])
    titles = _titles(
        ids
        + [d['document_id'] for ds in links.values() for d in ds]
        + [e['document_id'] for es in embeds.values() for e in es]
    )
    return {
        'total': len(shown),
        'sets': [
            {
                'same_document': same,
                'images': [
                    _image(images[i], created.get(i), users, links, embeds, titles)
                    for i in image_ids
                ],
            }
            for image_ids, same in rows
        ],
    }


def _sets():
    """Return the sets as computed within the hour: [(ids, same_document)]."""
    return get_or_create(
        cache_image_duplicates,
        f'sets-{caching.CACHE_VERSION}',
        _compute_sets,
        expiration_time=SETS_EXPIRATION,
    )


def _compute_sets():
    # the grouping of all the images sorts in memory then, not on disk (about
    # 30 MB for 650k images); for this transaction only
    DBSession.execute(text("SET LOCAL work_mem = '64MB'"))
    DBSession.execute(text(f"SET LOCAL statement_timeout = '{SETS_TIMEOUT}'"))
    rows = DBSession.execute(text(SETS_QUERY.format(no_exif_span=NO_EXIF_SPAN)))
    sets = [(list(row.ids), row.same_document) for row in rows]
    DBSession.execute(text('SET LOCAL statement_timeout = DEFAULT'))
    return sets


def _shown(sets, same_document):
    """Return the sets still to review: [(ids, same_document)]."""
    # Lookups by id: the images not merged nor deleted since, the pairs
    # dismissed.
    all_ids = sorted({image_id for ids, _ in sets for image_id in ids})
    if not all_ids:
        return []
    ids_param = bindparam('ids', all_ids, type_=ARRAY(Integer))
    live = set(
        DBSession.execute(
            select(Document.document_id).where(
                Document.document_id == func.any(ids_param),
                Document.redirects_to.is_(None),
            )
        ).scalars()
    )
    dismissed = {
        tuple(row)
        for row in DBSession.execute(
            select(
                DismissedImageDuplicate.image1_id, DismissedImageDuplicate.image2_id
            ).where(DismissedImageDuplicate.image1_id == func.any(ids_param))
        )
    }
    shown = []
    for ids, same in sets:
        if same_document and not same:
            continue
        ids = [image_id for image_id in ids if image_id in live]
        if any(pair not in dismissed for pair in combinations(ids, 2)):
            shown.append((ids, same))
    return shown


def _images(ids):
    if not ids:
        return {}
    rows = DBSession.execute(
        select(
            Image.document_id,
            Image.filename,
            Image.image_type,
            Image.file_size,
            Image.width,
            Image.height,
            Image.date_time,
            Image.camera_name,
        ).where(Image.document_id.in_(ids))
    )
    return {row.document_id: row for row in rows}


def _links(ids):
    """Return the documents each image is linked to: {id: [{id, type}]}."""
    if not ids:
        return {}
    result = {}
    parent_rows = DBSession.execute(
        select(
            Association.child_document_id,
            Association.parent_document_id,
            Association.parent_document_type,
        ).where(Association.child_document_id.in_(ids))
    )
    for image_id, document_id, document_type in parent_rows:
        result.setdefault(image_id, []).append(
            {'document_id': document_id, 'document_type': document_type}
        )
    child_rows = DBSession.execute(
        select(
            Association.parent_document_id,
            Association.child_document_id,
            Association.child_document_type,
        ).where(Association.parent_document_id.in_(ids))
    )
    for image_id, document_id, document_type in child_rows:
        result.setdefault(image_id, []).append(
            {'document_id': document_id, 'document_type': document_type}
        )
    for documents in result.values():
        documents.sort(key=lambda d: d['document_id'])
    return result


def _embeds(ids):
    """Return the texts showing each image by an [img=ID] tag: {id: [{...}]}."""
    # Also the texts showing an image merged into it (they show its files):
    # deleting the image breaks them too. Merging keeps them working.
    if not ids:
        return {}
    merged = DBSession.execute(
        select(Document.document_id, Document.redirects_to).where(
            Document.redirects_to.in_(ids)
        )
    ).all()
    shown = {image_id: image_id for image_id in ids}
    shown.update({source: target for source, target in merged})
    rows = DBSession.execute(
        select(
            ImageEmbed.image_id,
            ImageEmbed.document_id,
            ImageEmbed.lang,
            Document.type,
        )
        .join(Document, Document.document_id == ImageEmbed.document_id)
        .where(ImageEmbed.image_id.in_(list(shown)))
        .order_by(ImageEmbed.document_id, ImageEmbed.lang)
    )
    result = {}
    for image_id, document_id, lang, document_type in rows:
        result.setdefault(shown[image_id], []).append(
            {
                'document_id': document_id,
                'document_type': document_type,
                'lang': lang,
                'image_id': image_id,
            }
        )
    return result


def _image(row, created, users, links, embeds, titles):
    at, user_id = created or (None, None)
    return {
        'document_id': row.document_id,
        'filename': row.filename,
        'image_type': row.image_type,
        'title': titles.get(row.document_id),
        'file_size': row.file_size,
        'width': row.width,
        'height': row.height,
        'date_time': _iso(row.date_time),
        'camera_name': row.camera_name,
        'created_at': _iso(at),
        'author': _user(users, user_id),
        'documents': [
            {**d, 'title': titles.get(d['document_id'])}
            for d in links.get(row.document_id, [])
        ],
        'embedded_in': [
            {**e, 'title': titles.get(e['document_id'])}
            for e in embeds.get(row.document_id, [])
        ],
    }


def read_duplicate_images(request):
    """List the sets of duplicate images."""
    # `GET` `/images/duplicates?offset=0&limit=30&same_document=true`
    validated = request.validated
    return list_duplicate_images(
        validated.get('offset') or 0,
        min(validated.get('limit') or LIMIT_DEFAULT, LIMIT_MAX),
        same_document=bool(validated.get('same_document')),
    )


class DismissSchema(Schema):
    image_ids: Seq(Int, min_length=1)
    against: Seq(Int, min_length=1) = None


def _pairs(validated):
    image_ids = set(validated['image_ids'])
    against = validated.get('against')
    if against is None:
        return {tuple(sorted(p)) for p in combinations(image_ids, 2)}
    return {tuple(sorted((i, a))) for i in image_ids for a in set(against) if i != a}


def validate_images(request, **kwargs):
    """Check that the ids are images, and give at least one pair."""
    validated = request.validated
    if 'image_ids' not in validated:
        return
    ids = set(validated['image_ids']) | set(validated.get('against') or [])
    if len(ids) > DISMISS_MAX:
        request.errors.add('body', 'image_ids', f'{DISMISS_MAX} images at most')
        return
    found = set(
        DBSession.execute(
            # Image includes the table of the documents
            select(Image.document_id).where(
                Image.document_id.in_(ids), Document.redirects_to.is_(None)
            )
        ).scalars()
    )
    missing = sorted(ids - found)
    if missing:
        request.errors.add(
            'body', 'image_ids', f'not images: {", ".join(map(str, missing))}'
        )
        return
    if not _pairs(validated):
        request.errors.add('body', 'image_ids', 'no pair of images to dismiss')


@write(
    validators=[body_validator(DismissSchema), validate_images],
    permission='moderator',
    json=True,
)
def dismiss_duplicate_images(request):
    """Tell that images listed as duplicates are not."""
    # `POST` `/images/duplicates/dismiss`
    # {'image_ids': [@document_id@, ...], 'against': [@document_id@, ...]}
    # Without `against`: all the pairs of `image_ids` (a whole set). With
    # `against`: each image of `image_ids` with each one of `against` (one
    # image is not a copy of the others of its set).
    pairs = sorted(_pairs(request.validated))
    DBSession.execute(
        insert(DismissedImageDuplicate)
        .values(
            [
                {
                    'image1_id': image1_id,
                    'image2_id': image2_id,
                    'dismissed_by': request.authenticated_userid,
                }
                for image1_id, image2_id in pairs
            ]
        )
        .on_conflict_do_nothing()
    )
    return {'dismissed': len(pairs)}
