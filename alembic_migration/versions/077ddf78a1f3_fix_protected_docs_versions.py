"""Fix protected docs versions

Revision ID: 077ddf78a1f3
Revises: 9739938498a8
Create Date: 2017-10-30 12:05:51.679435

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '077ddf78a1f3'
down_revision = '9739938498a8'
branch_labels = None
depends_on = None

def upgrade():
    op.execute("""
        with versions_from_archives as (
          select document_id, max(version) as version
          from guidebook.documents_archives
          group by document_id
        )
        update guidebook.documents as d
        set version = va.version
        from versions_from_archives va
        where d.document_id = va.document_id""")


def downgrade():
    # Not reversible
    pass
