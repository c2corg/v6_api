"""Add the view of the articles associated to each outing.

Used to index the articles of the outings, so that the outings can be
searched by article (`/outings?c=<article id>`).

Revision ID: a7c3e5f19d42
Revises: f3a8c1d6e2b7
Create Date: 2026-11-27 12:00:00.000000

"""

from alembic import op

from alembic_migration import extensions

# revision identifiers, used by Alembic.
revision = 'a7c3e5f19d42'
down_revision = 'f3a8c1d6e2b7'
branch_labels = None
depends_on = None

view_articles_for_outings = extensions.ReplaceableObject(
    'guidebook.articles_for_outings',
    """
SELECT guidebook.associations.parent_document_id AS outing_id, array_agg(guidebook.associations.child_document_id) AS article_ids
FROM guidebook.associations
WHERE guidebook.associations.parent_document_type = 'o' AND guidebook.associations.child_document_type = 'c' GROUP BY guidebook.associations.parent_document_id;
""",  # noqa: E501
)


def upgrade():
    op.create_view(view_articles_for_outings)


def downgrade():
    op.drop_view(view_articles_for_outings)
