"""bot_texts unique constraint on key+language

Revision ID: 0002
Revises: 0001
Create Date: 2025-01-02 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_bot_texts_key_language",
        "bot_texts",
        ["key", "language"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_bot_texts_key_language", "bot_texts", type_="unique")
