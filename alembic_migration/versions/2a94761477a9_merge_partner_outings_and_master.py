"""merge partner outings and master

The partner migrations (meta) and master's merged documents both follow
5e3c1a7b9d42: this joins the two heads, nothing else.

Revision ID: 2a94761477a9
Revises: f1b6d3a8e2c9, f3a8c1d6e2b7
Create Date: 2026-11-27 14:44:38.037908

"""

# revision identifiers, used by Alembic.
revision = '2a94761477a9'
down_revision = ('f1b6d3a8e2c9', 'f3a8c1d6e2b7')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
