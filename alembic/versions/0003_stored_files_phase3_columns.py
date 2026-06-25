"""stored_files: add text_content, metadata_json, original_file_name, file_size, mime_type

Revision ID: 0003
Revises: 0002
Create Date: 2025-01-03 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("stored_files", sa.Column("text_content", sa.Text(), nullable=True))
    op.add_column("stored_files", sa.Column("metadata_json", JSONB(), nullable=True))
    op.add_column("stored_files", sa.Column("original_file_name", sa.String(512), nullable=True))
    op.add_column("stored_files", sa.Column("file_size", sa.BigInteger(), nullable=True))
    op.add_column("stored_files", sa.Column("mime_type", sa.String(255), nullable=True))

    # telegram_file_id and telegram_file_unique_id can now be empty for text/contact/location
    op.alter_column("stored_files", "telegram_file_id", server_default="", nullable=False)
    op.alter_column("stored_files", "telegram_file_unique_id", server_default="", nullable=False)


def downgrade() -> None:
    op.drop_column("stored_files", "mime_type")
    op.drop_column("stored_files", "file_size")
    op.drop_column("stored_files", "original_file_name")
    op.drop_column("stored_files", "metadata_json")
    op.drop_column("stored_files", "text_content")
