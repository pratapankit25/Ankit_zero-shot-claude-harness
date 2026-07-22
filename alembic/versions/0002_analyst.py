"""analyst: datasets, conversations, run audit columns

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RUN_COLUMNS = [
    sa.Column("conversation_id", sa.Text(), nullable=True),
    sa.Column("language", sa.Text(), nullable=True),
    sa.Column("sql_text", sa.Text(), nullable=True),
    sa.Column("steps_json", sa.Text(), nullable=True),
    sa.Column("result_json", sa.Text(), nullable=True),
    sa.Column("caveats_json", sa.Text(), nullable=True),
    sa.Column("followups_json", sa.Text(), nullable=True),
    sa.Column("input_tokens", sa.Integer(), nullable=True),
    sa.Column("output_tokens", sa.Integer(), nullable=True),
    sa.Column("duration_ms", sa.Integer(), nullable=True),
]


def upgrade() -> None:
    for col in _RUN_COLUMNS:
        op.add_column("runs", col)
    op.create_index("ix_runs_conversation_id", "runs", ["conversation_id"])

    op.create_table(
        "conversations",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "datasets",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("table_name", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("columns_json", sa.Text(), nullable=True),
        sa.Column("profile_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("table_name"),
    )


def downgrade() -> None:
    op.drop_table("datasets")
    op.drop_table("conversations")
    op.drop_index("ix_runs_conversation_id", table_name="runs")
    for col in reversed(_RUN_COLUMNS):
        op.drop_column("runs", col.name)
