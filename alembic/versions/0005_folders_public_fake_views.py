"""folders, public/private mode, fake views

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-25
"""
from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'folders',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_folders_owner_id', 'folders', ['owner_id'])

    op.add_column('stored_files', sa.Column('fake_views', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('stored_files', sa.Column('is_public', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column(
        'stored_files',
        sa.Column('folder_id', sa.Integer(), sa.ForeignKey('folders.id', ondelete='SET NULL'), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('stored_files', 'folder_id')
    op.drop_column('stored_files', 'is_public')
    op.drop_column('stored_files', 'fake_views')
    op.drop_index('ix_folders_owner_id', table_name='folders')
    op.drop_table('folders')
