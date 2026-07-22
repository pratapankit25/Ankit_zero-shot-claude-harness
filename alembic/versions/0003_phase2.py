"""phase 2: chart + anomaly-flag columns on runs

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("chart_json", sa.Text(), nullable=True))
    op.add_column("runs", sa.Column("flags_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "flags_json")
    op.drop_column("runs", "chart_json")
