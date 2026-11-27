"""Merge partner outings and master, again.

Master now has two heads of its own (the article views of the outings and
the link checks): this joins them with the partner outings, nothing else.

Revision ID: c4e2a9d7b1f3
Revises: 2a94761477a9, a7c3e5f19d42, b8d4f0a2c3e5
Create Date: 2026-11-27 17:30:00.000000

"""

# revision identifiers, used by Alembic.
revision = 'c4e2a9d7b1f3'
down_revision = ('2a94761477a9', 'a7c3e5f19d42', 'b8d4f0a2c3e5')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
