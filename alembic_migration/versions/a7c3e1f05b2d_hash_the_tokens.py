"""Hash the tokens.

Revision ID: a7c3e1f05b2d
Revises: 335e0bc4df28
Create Date: 2026-11-05 12:00:00.000000

"""

import hashlib

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'a7c3e1f05b2d'
down_revision = '335e0bc4df28'
branch_labels = None
depends_on = None


def upgrade():
    # The column keeps its name and holds the SHA-256 of the token, as
    # c2corg_api.security.roles.hash_token computes it: the sessions stay
    # open. Hashed here, not in SQL: sha256() needs PostgreSQL 11, and
    # production runs 9.6.
    conn = op.get_bind()
    tokens = conn.execute(sa.text('SELECT value FROM users.token')).scalars().all()
    if tokens:
        conn.execute(
            sa.text('UPDATE users.token SET value = :hash WHERE value = :token'),
            [
                {
                    'token': token,
                    'hash': hashlib.sha256(token.encode('utf-8')).hexdigest(),
                }
                for token in tokens
            ],
        )


def downgrade():
    # A hash cannot be turned back into a token: every session is closed.
    op.execute('DELETE FROM users.token')
