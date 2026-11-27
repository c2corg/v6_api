import datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

from c2corg_api.models import Base
from c2corg_api.models.partner_outing import (
    GEOM_QUALITIES,
    SOURCE_STATUSES,
    PartnerLookup,
    PartnerOuting,
    PartnerSource,
)

TABLES = ('partner_outings', 'partner_sources', 'partner_lookups')


def _outing(**kwargs):
    values = {
        'source': 'skitour',
        'external_id': '1',
        'url': 'https://skitour.example/1',
        'title': 'Pointe de la Sana',
        'date': datetime.date(2026, 2, 14),
        'activities': ['skitouring'],
    }
    values.update(kwargs)
    return PartnerOuting(**values)


def test_insert_and_read_back(session):
    outing = _outing(
        lang='fr',
        activities=['skitouring', 'snow_ice_mixed'],
        orientations=['N', 'NE'],
        ski_rating_min='2.1',
        ski_rating_max='3.2',
        geom='SRID=3857;POINT(635956 5723604)',
        geom_quality='summit',
        snow={'depth_cm': 120},
        steep=True,
        elevation_max=2500,
        height_diff_up=1100,
    )
    session.add(outing)
    session.flush()
    session.expire_all()

    outing = session.get(PartnerOuting, outing.id)
    assert outing.activities == ['skitouring', 'snow_ice_mixed']
    assert outing.orientations == ['N', 'NE']
    assert outing.ski_rating_min == '2.1'
    assert outing.ski_rating_max == '3.2'
    assert outing.snow == {'depth_cm': 120}
    assert outing.steep is True
    assert outing.geom_quality == 'summit'
    assert (
        session.scalar(
            sa.select(sa.func.ST_SRID(PartnerOuting.geom)).where(
                PartnerOuting.id == outing.id
            )
        )
        == 3857
    )
    assert session.scalar(
        sa.select(sa.func.ST_X(PartnerOuting.geom)).where(PartnerOuting.id == outing.id)
    ) == pytest.approx(635956)


def test_defaults(session):
    outing = _outing()
    session.add(outing)
    session.flush()
    session.expire_all()

    outing = session.get(PartnerOuting, outing.id)
    assert outing.area_ids == []
    assert outing.steep is False
    assert outing.geom_quality == 'none'
    assert outing.geom is None
    assert outing.orientations is None
    assert outing.first_seen_at is not None
    assert outing.fetched_at is not None


def test_area_ids_round_trip(session):
    outing = _outing(area_ids=[3, 14])
    session.add(outing)
    session.flush()
    session.expire_all()
    assert session.get(PartnerOuting, outing.id).area_ids == [3, 14]


def test_source_external_id_is_unique(session):
    session.add(_outing())
    session.flush()
    # the same id in another source is fine
    session.add(_outing(source='gulliver'))
    session.flush()

    session.add(_outing(title='Again'))
    with pytest.raises(IntegrityError):
        session.flush()


def test_geom_quality_check(session):
    for quality in GEOM_QUALITIES:
        session.add(_outing(external_id=quality, geom_quality=quality))
    session.flush()

    session.add(_outing(external_id='bad', geom_quality='bad'))
    with pytest.raises(IntegrityError):
        session.flush()


def test_activities_required(session):
    session.add(_outing(activities=None))
    with pytest.raises(IntegrityError):
        session.flush()


def test_source_status_check(session):
    for status in SOURCE_STATUSES:
        session.add(PartnerSource(source=status, status=status))
    session.flush()

    session.add(PartnerSource(source='bad', status='bad'))
    with pytest.raises(IntegrityError):
        session.flush()


def test_source_defaults(session):
    session.add(PartnerSource(source='skitour'))
    session.flush()
    session.expire_all()

    source = session.get(PartnerSource, 'skitour')
    assert source.status == 'never_run'
    assert source.consecutive_failures == 0
    assert source.last_skipped == {}
    assert source.cursor is None


def test_source_jsonb(session):
    session.add(
        PartnerSource(
            source='skitour',
            last_skipped={'unmapped_activity:climb': 4},
            cursor={'since': '2026-02-14'},
        )
    )
    session.flush()
    session.expire_all()

    source = session.get(PartnerSource, 'skitour')
    assert source.last_skipped == {'unmapped_activity:climb': 4}
    assert source.cursor == {'since': '2026-02-14'}


def test_lookup_round_trip(session):
    data = {'name': 'Sana', 'ratings': [1, 2], 'nested': {'ok': True}}
    session.add(PartnerLookup(source='gulliver', key='route:57949', data=data))
    session.flush()
    session.expire_all()

    lookup = session.get(PartnerLookup, ('gulliver', 'route:57949'))
    assert lookup.data == data
    assert lookup.fetched_at is not None


def _signature(column, dialect):
    """The comparable form of a column: name, type and nullability."""
    type_ = column.type
    if isinstance(type_, postgresql.ARRAY):
        item = type_.item_type
        name = getattr(item, 'name', None)
        # an array of enum, as reflected, is of `schema.name`
        type_name = f'{name}[]' if name else f'{item.compile(dialect=dialect)}[]'
    else:
        type_name = getattr(type_, 'name', None) or type_.compile(dialect=dialect)
    return (
        column.name,
        str(type_name).lower().replace('guidebook.', ''),
        column.nullable,
    )


@pytest.mark.parametrize('table_name', TABLES)
def test_orm_matches_migrated_database(db_connection, table_name):
    """The models and the migration must not drift."""
    dialect = db_connection.dialect
    model_table = Base.metadata.tables[f'guidebook.{table_name}']
    inspector = sa.inspect(db_connection)

    reflected = sa.Table(
        table_name,
        sa.MetaData(),
        schema='guidebook',
        autoload_with=db_connection,
    )

    def signatures(table):
        return {c.name: _signature(c, dialect) for c in table.columns}

    expected = signatures(model_table)
    actual = signatures(reflected)
    assert actual == expected

    # the primary keys, the unique constraints and the indexes
    assert [c.name for c in reflected.primary_key.columns] == [
        c.name for c in model_table.primary_key.columns
    ]
    assert {
        i['name']
        for i in inspector.get_indexes(table_name, schema='guidebook')
        # PostgreSQL lists the index of a unique constraint too
        if not i['name'].startswith('uq_')
    } == {i.name for i in model_table.indexes}
    assert {
        u['name']
        for u in inspector.get_unique_constraints(table_name, schema='guidebook')
    } == {
        c.name
        for c in model_table.constraints
        if isinstance(c, sa.UniqueConstraint) and c.name
    }
    assert {
        c['name']
        for c in inspector.get_check_constraints(table_name, schema='guidebook')
    } == {c.name for c in model_table.constraints if isinstance(c, sa.CheckConstraint)}
