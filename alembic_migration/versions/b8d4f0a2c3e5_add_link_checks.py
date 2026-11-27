"""Check the links to other sites: the URLs and the hosts.

Revision ID: b8d4f0a2c3e5
Revises: a7c3e9f1b2d4
Create Date: 2026-11-27 14:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'b8d4f0a2c3e5'
down_revision = 'a7c3e9f1b2d4'
branch_labels = None
depends_on = None


def _review_columns():
    return [
        sa.Column('review', sa.String(length=20), nullable=True),
        sa.Column('reviewed_by', sa.Integer(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['reviewed_by'], ['users.user.id']),
    ]


def upgrade():
    # Created empty: the link checker job fills them (see c2corg_api.linkcheck)
    op.create_table(
        'link_hosts',
        sa.Column('host', sa.String(length=255), nullable=False),
        sa.Column('next_request_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('robots_txt', sa.Text(), nullable=True),
        sa.Column('robots_fetched_at', sa.DateTime(timezone=True), nullable=True),
        *_review_columns(),
        sa.PrimaryKeyConstraint('host'),
        schema='guidebook',
    )
    op.create_table(
        'link_checks',
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('host', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('http_status', sa.SmallInteger(), nullable=True),
        sa.Column('error', sa.String(length=30), nullable=True),
        sa.Column('final_url', sa.Text(), nullable=True),
        sa.Column('first_title', sa.String(length=300), nullable=True),
        sa.Column('last_title', sa.String(length=300), nullable=True),
        sa.Column('failures', sa.SmallInteger(), nullable=False),
        sa.Column('first_failure_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_ok_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_checked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_check_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
        *_review_columns(),
        sa.PrimaryKeyConstraint('url'),
        schema='guidebook',
    )
    for column in ('host', 'next_check_at', 'status'):
        op.create_index(
            f'ix_guidebook_link_checks_{column}',
            'link_checks',
            [column],
            unique=False,
            schema='guidebook',
        )


def downgrade():
    op.drop_table('link_checks', schema='guidebook')
    op.drop_table('link_hosts', schema='guidebook')
