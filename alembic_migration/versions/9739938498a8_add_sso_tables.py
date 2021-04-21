"""Add SSO tables

Revision ID: 9739938498a8
Revises: 8c230a4a0284
Create Date: 2017-08-17 15:25:46.868974

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '9739938498a8'
down_revision = '8c230a4a0284'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('sso_key',
                    sa.Column('domain', sa.String(), nullable=False),
                    sa.Column('key', sa.String(), nullable=False),
                    sa.PrimaryKeyConstraint('domain'),
                    sa.UniqueConstraint('key'),
                    schema='users')
    op.create_table('sso_external_id',
                    sa.Column('domain', sa.String(), nullable=False),
                    sa.Column('external_id', sa.Integer(), nullable=False),
                    sa.Column('user_id', sa.Integer(), nullable=False),
                    sa.Column('token', sa.String()),
                    sa.Column('expire', sa.DateTime(timezone=True)),
                    sa.ForeignKeyConstraint(
                        ['domain'], ['users.sso_key.domain'], ),
                    sa.ForeignKeyConstraint(['user_id'], ['users.user.id'], ),
                    sa.PrimaryKeyConstraint('domain', 'external_id'),
                    schema='users')


def downgrade():
    op.drop_table('sso_external_id', schema='users')
    op.drop_table('sso_key', schema='users')
