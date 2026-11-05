"""Hash the tokens.

Revision ID: a7c3e1f05b2d
Revises: 335e0bc4df28
Create Date: 2026-11-05 12:00:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = 'a7c3e1f05b2d'
down_revision = '335e0bc4df28'
branch_labels = None
depends_on = None


def upgrade():
    # The column keeps its name and holds the SHA-256 of the token
    # (c2corg_api.security.roles.hash_token): the sessions stay open.
    op.execute(
        'UPDATE users.token '
        "SET value = encode(sha256(convert_to(value, 'UTF8')), 'hex')"
    )


def downgrade():
    # A hash cannot be turned back into a token: every session is closed.
    op.execute('DELETE FROM users.token')
