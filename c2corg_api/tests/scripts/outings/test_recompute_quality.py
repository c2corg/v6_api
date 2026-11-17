from datetime import date

import pytest

from c2corg_api.models import DBSession
from c2corg_api.models.association import Association
from c2corg_api.models.document_history import DocumentVersion, HistoryMetaData
from c2corg_api.models.image import Image
from c2corg_api.models.outing import Outing, OutingLocale
from c2corg_api.scripts.outings.recompute_quality import recompute_quality
from c2corg_api.views.document import create_new_version


@pytest.fixture
def make_outing(db_connection, user_ids):
    def make(quality, images=0, **locale):
        outing = Outing(
            activities=['rock_climbing'],
            date_start=date(2026, 6, 1),
            date_end=date(2026, 6, 1),
            quality=quality,
            locales=[OutingLocale(lang='fr', title='Visite obligatoire', **locale)],
        )
        DBSession.add(outing)
        DBSession.flush()
        create_new_version(outing, user_ids['contributor'])
        for index in range(images):
            image = Image(filename=f'image{outing.document_id}_{index}.jpg')
            DBSession.add(image)
            DBSession.flush()
            DBSession.add(
                Association.create(parent_document=outing, child_document=image)
            )
        DBSession.flush()
        return outing

    return make


def quality(outing):
    DBSession.expire_all()
    return DBSession.get(Outing, outing.document_id).quality


def comments(outing):
    return [
        comment
        for (comment,) in DBSession.query(HistoryMetaData.comment)
        .join(DocumentVersion)
        .filter(DocumentVersion.document_id == outing.document_id)
        .order_by(HistoryMetaData.id)
    ]


@pytest.fixture
def outings(make_outing):
    return {
        # empty by the old rules, with a route description: draft
        'empty': make_outing('empty', route_description='the left variant'),
        # draft by the old rules, a personal comment and photos: medium
        'draft': make_outing(
            'draft', images=2, route_description='approach', description='rock'
        ),
        # fine by the old rules, four lines on the weather: medium
        'fine': make_outing(
            'fine', conditions='not too hot', weather='cumulus', timing='5h'
        ),
        # chosen by the author (fine, computed as draft by both rules): kept
        'chosen': make_outing('fine', description='rock'),
        'great': make_outing('great', description='rock'),
        # already the quality of the latest rules
        'unchanged': make_outing('draft', description='rock'),
    }


def run(outings, user_id=None):
    return recompute_quality(
        DBSession,
        user_id=user_id,
        comment='Recomputed',
        queue_config=None,
        batch_size=2,
        ids=[outing.document_id for outing in outings.values()],
    )


def test_dry_run(outings):
    changes = run(outings)
    assert changes == {
        ('empty', 'draft'): 1,
        ('draft', 'medium'): 1,
        ('fine', 'medium'): 1,
    }
    # nothing saved
    assert {name: quality(outing) for name, outing in outings.items()} == {
        'empty': 'empty',
        'draft': 'draft',
        'fine': 'fine',
        'chosen': 'fine',
        'great': 'great',
        'unchanged': 'draft',
    }


def test_recompute(outings, user_ids):
    changes = run(outings, user_ids['moderator'])
    assert sum(changes.values()) == 3
    assert {name: quality(outing) for name, outing in outings.items()} == {
        'empty': 'draft',
        'draft': 'medium',
        'fine': 'medium',
        'chosen': 'fine',
        'great': 'great',
        'unchanged': 'draft',
    }

    # a new version, by the given user
    assert comments(outings['empty'])[-1] == 'Recomputed'
    assert comments(outings['chosen'])[-1] != 'Recomputed'
    version = (
        DBSession.query(HistoryMetaData)
        .join(DocumentVersion)
        .filter(DocumentVersion.document_id == outings['draft'].document_id)
        .order_by(HistoryMetaData.id.desc())
        .first()
    )
    assert version.user_id == user_ids['moderator']

    # a second run changes nothing
    assert run(outings, user_ids['moderator']) == {}
