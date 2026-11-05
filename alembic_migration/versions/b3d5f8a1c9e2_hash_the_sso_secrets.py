"""Hash the SSO keys and login tokens.

Revision ID: b3d5f8a1c9e2
Revises: a7c3e1f05b2d
Create Date: 2026-11-05 18:00:00.000000

"""

import hashlib

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'b3d5f8a1c9e2'
down_revision = 'a7c3e1f05b2d'
branch_labels = None
depends_on = None

# a SHA-256 in hex: what the new code stores; the secrets themselves are not
# (a key chosen by an admin, a login token in base64)
HASHED = '^[0-9a-f]{64}$'


def _hash(conn, table, column):
    rows = (
        conn.execute(
            sa.text(
                f'SELECT {column} FROM users.{table} '
                f'WHERE {column} IS NOT NULL AND {column} !~ :hashed'
            ),
            {'hashed': HASHED},
        )
        .scalars()
        .all()
    )
    if rows:
        conn.execute(
            sa.text(
                f'UPDATE users.{table} SET {column} = :hash WHERE {column} = :value'
            ),
            [
                {
                    'value': value,
                    'hash': hashlib.sha256(value.encode('utf-8')).hexdigest(),
                }
                for value in rows
            ],
        )


def upgrade():
    # Hashed in Python, not in SQL: sha256() needs PostgreSQL 11, and
    # production runs 9.6. Only the values not hashed yet: the new code may
    # already have stored hashes (deployed first), and it can run twice.
    conn = op.get_bind()
    _hash(conn, 'sso_key', 'key')
    _hash(conn, 'sso_external_id', 'token')


def downgrade():
    # A hash cannot be turned back into a secret: the login tokens (10 min)
    # are dropped; the keys must be set again by an admin.
    op.execute('UPDATE users.sso_external_id SET token = NULL')
