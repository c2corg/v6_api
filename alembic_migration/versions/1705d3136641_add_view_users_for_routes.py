"""Add view users_for_routes

Revision ID: 1705d3136641
Revises: bece9007ab83
Create Date: 2020-04-23 21:14:37.755919

"""
from alembic import op
from alembic_migration import extensions


# revision identifiers, used by Alembic.
revision = '1705d3136641'
down_revision = 'bece9007ab83'
branch_labels = None
depends_on = None

view_users_for_routes = extensions.ReplaceableObject(
    'guidebook.users_for_routes',
    """
SELECT guidebook.documents_tags.document_id AS route_id, array_agg(guidebook.documents_tags.user_id) AS user_ids
FROM guidebook.documents_tags
GROUP BY guidebook.documents_tags.document_id;
""")

def upgrade():
    op.create_view(view_users_for_routes)


def downgrade():
    op.drop_view(view_users_for_routes)
