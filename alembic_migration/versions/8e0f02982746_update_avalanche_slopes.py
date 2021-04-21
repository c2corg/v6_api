"""Update avalanche slopes

Revision ID: 8e0f02982746
Revises: 940bd29040d8
Create Date: 2017-04-10 17:54:17.175098

"""
from alembic import op
import sqlalchemy as sa
from alembic_migration.extensions import drop_enum
from sqlalchemy.sql.schema import Table, MetaData


# revision identifiers, used by Alembic.
revision = '8e0f02982746'
down_revision = '940bd29040d8'
branch_labels = None
depends_on = None

# See http://stackoverflow.com/questions/14845203/altering-an-enum-field-using-alembic

def upgrade():
    conversions = [
        ('slope_lt_30', 'slope_lt_30'),
        ('slope_30_32', 'slope_30_35'),
        ('slope_33_35', 'slope_30_35'),
        ('slope_36_38', 'slope_35_40'),
        ('slope_39_41', 'slope_35_40'),
        ('slope_42_44', 'slope_40_45'),
        ('slope_45_47', 'slope_gt_45'),
        ('slope_gt_47', 'slope_gt_45')]
    
    old_options = (
        'slope_lt_30', 'slope_30_32', 'slope_33_35', 'slope_36_38',
        'slope_39_41', 'slope_42_44', 'slope_45_47', 'slope_gt_47')
    new_options = (
        'slope_lt_30', 'slope_30_35', 'slope_35_40', 'slope_40_45',
        'slope_gt_45')
    
    old_type = sa.Enum(
        *old_options, name='avalanche_slope', schema='guidebook')
    new_type = sa.Enum(
        *new_options, name='avalanche_slope_', schema='guidebook')
    new_type.create(op.get_bind(), checkfirst=False)

    # Create new column with temporary name
    op.add_column(
        'xreports',
        sa.Column('avalanche_slope_', new_type, nullable=True),
        schema='guidebook')

    op.add_column(
        'xreports_archives',
        sa.Column('avalanche_slope_', new_type, nullable=True),
        schema='guidebook')

    # Fill new column using the old 'avalanche_slope' column values
    xreports = Table(
        'xreports',
        MetaData(),
        sa.Column('avalanche_slope', old_type, nullable=True),
        sa.Column('avalanche_slope_', new_type, nullable=True),
        schema='guidebook')
    for (old_value, new_value) in conversions:
        op.execute(
            xreports.update(). \
            where(xreports.c.avalanche_slope==op.inline_literal(old_value)). \
            values({'avalanche_slope_':op.inline_literal(new_value)})
        )

    archives = Table(
        'xreports_archives',
        MetaData(),
        sa.Column('avalanche_slope', old_type, nullable=True),
        sa.Column('avalanche_slope_', new_type, nullable=True),
        schema='guidebook')
    for (old_value, new_value) in conversions:
        op.execute(
            archives.update(). \
            where(archives.c.avalanche_slope==op.inline_literal(old_value)). \
            values({'avalanche_slope_':op.inline_literal(new_value)})
        )

    # Drop old column and enum
    op.drop_column('xreports', 'avalanche_slope', schema='guidebook')
    op.drop_column('xreports_archives', 'avalanche_slope', schema='guidebook')
    drop_enum('avalanche_slope', schema='guidebook')

    # Rename enum
    op.execute('ALTER TYPE guidebook.avalanche_slope_ RENAME TO avalanche_slope')

    # Rename column
    op.alter_column(
        'xreports',
        'avalanche_slope_',
        new_column_name='avalanche_slope',
        schema='guidebook')

    op.alter_column(
        'xreports_archives',
        'avalanche_slope_',
        new_column_name='avalanche_slope',
        schema='guidebook')


def downgrade():
    # Not reversible because the transformation is not bijective.
    pass
