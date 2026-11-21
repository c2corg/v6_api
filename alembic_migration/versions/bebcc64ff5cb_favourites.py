"""Turn the documents tags into favourites, with folders.

Revision ID: bebcc64ff5cb
Revises: 39ccf15da971
Create Date: 2026-11-21 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'bebcc64ff5cb'
down_revision = '39ccf15da971'
branch_labels = None
depends_on = None

# PostgreSQL 9.6 in production: plain renames, no newer SQL.

# (old name, new name) of the tables, their indexes, constraints, sequence
TABLES = [
    ('documents_tags', 'favourites'),
    ('documents_tags_log', 'favourites_log'),
]
INDEXES = [
    ('ix_guidebook_documents_tags_user_id', 'ix_guidebook_favourites_user_id'),
    ('ix_guidebook_documents_tags_document_id', 'ix_guidebook_favourites_document_id'),
    (
        'ix_guidebook_documents_tags_document_type',
        'ix_guidebook_favourites_document_type',
    ),
    (
        'ix_guidebook_documents_tags_log_written_at',
        'ix_guidebook_favourites_log_written_at',
    ),
]
# by table (new name); a primary key renames its index too
CONSTRAINTS = {
    'favourites': [
        ('documents_tags_pkey', 'favourites_pkey'),
        ('documents_tags_user_id_fkey', 'favourites_user_id_fkey'),
        ('documents_tags_document_id_fkey', 'favourites_document_id_fkey'),
    ],
    'favourites_log': [
        ('documents_tags_log_pkey', 'favourites_log_pkey'),
        ('documents_tags_log_user_id_fkey', 'favourites_log_user_id_fkey'),
        ('documents_tags_log_document_id_fkey', 'favourites_log_document_id_fkey'),
    ],
}
SEQUENCES = [('documents_tags_log_id_seq', 'favourites_log_id_seq')]

# the route search index lists the users having a route in favourites
# (field `u`): only the routes
VIEW_SQL = """
CREATE OR REPLACE VIEW guidebook.users_for_routes AS
SELECT {table}.document_id AS route_id, array_agg({table}.user_id) AS user_ids
FROM guidebook.{table}
{where}
GROUP BY {table}.document_id
"""


def _rename(pairs, kind):
    for old, new in pairs:
        op.execute(f'ALTER {kind} guidebook.{old} RENAME TO {new}')


def _rename_constraints(forward):
    # the tables have their new names then, in both directions
    for table, pairs in CONSTRAINTS.items():
        for old, new in pairs:
            if not forward:
                old, new = new, old
            op.execute(
                f'ALTER TABLE guidebook.{table} RENAME CONSTRAINT {old} TO {new}'
            )


def _rename_snapshot_tables(pairs):
    # the rows kept by the deleted documents (views.document_trash), by table;
    # the names as bound parameters, not in the SQL text
    update = sa.text(
        """
        UPDATE guidebook.deleted_documents
        SET snapshot = jsonb_set(
            snapshot #- CAST(:old_path AS text[]),
            CAST(:new_path AS text[]),
            snapshot -> 'tables' -> :old_key
        )
        WHERE snapshot -> 'tables' ? :old_key
        """
    )
    for old, new in pairs:
        op.execute(
            update.bindparams(
                old_key=f'guidebook.{old}',
                old_path=f'{{tables,guidebook.{old}}}',
                new_path=f'{{tables,guidebook.{new}}}',
            )
        )


def upgrade():
    _rename(TABLES, 'TABLE')
    _rename(INDEXES, 'INDEX')
    _rename_constraints(forward=True)
    _rename(SEQUENCES, 'SEQUENCE')
    _rename_snapshot_tables(TABLES)

    op.create_table(
        'favourite_folders',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('position', sa.Integer(), server_default='0', nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.user.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'name'),
        schema='guidebook',
    )
    op.create_index(
        'ix_guidebook_favourite_folders_user_id',
        'favourite_folders',
        ['user_id'],
        unique=False,
        schema='guidebook',
    )

    op.add_column(
        'favourites',
        sa.Column('folder_id', sa.Integer(), nullable=True),
        schema='guidebook',
    )
    op.create_foreign_key(
        'favourites_folder_id_fkey',
        'favourites',
        'favourite_folders',
        ['folder_id'],
        ['id'],
        source_schema='guidebook',
        referent_schema='guidebook',
        ondelete='SET NULL',
    )
    op.create_index(
        'ix_guidebook_favourites_folder_id',
        'favourites',
        ['folder_id'],
        unique=False,
        schema='guidebook',
    )
    op.add_column(
        'favourites',
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        schema='guidebook',
    )
    # the date of the latest addition, where it was logged
    op.execute(
        """
        UPDATE guidebook.favourites f
        SET created_at = l.written_at
        FROM (
            SELECT user_id, document_id, max(written_at) AS written_at
            FROM guidebook.favourites_log
            WHERE is_creation
            GROUP BY user_id, document_id
        ) l
        WHERE l.user_id = f.user_id AND l.document_id = f.document_id
        """
    )

    op.execute(
        VIEW_SQL.format(
            table='favourites', where="WHERE favourites.document_type = 'r'"
        )
    )


def downgrade():
    op.execute(VIEW_SQL.format(table='favourites', where=''))

    op.drop_column('favourites', 'created_at', schema='guidebook')
    op.drop_index(
        'ix_guidebook_favourites_folder_id', table_name='favourites', schema='guidebook'
    )
    op.drop_constraint(
        'favourites_folder_id_fkey',
        'favourites',
        type_='foreignkey',
        schema='guidebook',
    )
    op.drop_column('favourites', 'folder_id', schema='guidebook')
    op.drop_index(
        'ix_guidebook_favourite_folders_user_id',
        table_name='favourite_folders',
        schema='guidebook',
    )
    op.drop_table('favourite_folders', schema='guidebook')

    reverse = [(new, old) for old, new in TABLES]
    _rename_snapshot_tables(reverse)
    _rename([(new, old) for old, new in SEQUENCES], 'SEQUENCE')
    _rename_constraints(forward=False)
    _rename([(new, old) for old, new in INDEXES], 'INDEX')
    _rename(reverse, 'TABLE')
