"""phase 3: mssql sync tables, freshness, schedules & reports

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("datasets", sa.Column("synced_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("runs", sa.Column("freshness", sa.Text(), nullable=True))

    op.create_table(
        "sync_tables",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("source_table", sa.Text(), nullable=False),
        sa.Column("dataset_name", sa.Text(), nullable=False),
        sa.Column("incremental_column", sa.Text(), nullable=True),
        sa.Column("last_synced_value", sa.Text(), nullable=True),
        sa.Column("dataset_id", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_table"),
    )
    op.create_table(
        "sync_runs",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("source_table", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("rows", sa.Integer(), nullable=True),
        sa.Column("mode", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "schedules",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("cadence", sa.Text(), nullable=False),          # daily | weekly
        sa.Column("hour", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("weekday", sa.Integer(), nullable=True),        # 0=Mon, weekly only
        sa.Column("questions_json", sa.Text(), nullable=False),
        sa.Column("language", sa.Text(), nullable=False, server_default="en"),
        sa.Column("recipients_json", sa.Text(), nullable=True),   # used by phase-4 email
        sa.Column("enabled", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_run_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "reports",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("schedule_id", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content_md", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("reports")
    op.drop_table("schedules")
    op.drop_table("sync_runs")
    op.drop_table("sync_tables")
    op.drop_column("runs", "freshness")
    op.drop_column("datasets", "synced_at")
