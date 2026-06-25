"""phase4 user settings and file auto delete

Revision ID: 0004
Revises: 0003
Create Date: 2025-06-25
"""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('signature', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('default_expiration_seconds', sa.Integer(), nullable=True))
    op.add_column('users', sa.Column('auto_delete_seconds', sa.Integer(), nullable=True))
    op.add_column('stored_files', sa.Column('auto_delete_seconds', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('stored_files', 'auto_delete_seconds')
    op.drop_column('users', 'auto_delete_seconds')
    op.drop_column('users', 'default_expiration_seconds')
    op.drop_column('users', 'signature')
