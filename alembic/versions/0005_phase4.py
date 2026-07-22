"""phase 4: users, sessions, district scoping, deliveries

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("datasets", sa.Column("district", sa.Text(), nullable=True))
    op.add_column("runs", sa.Column("user_id", sa.Text(), nullable=True))
    op.add_column("conversations", sa.Column("user_id", sa.Text(), nullable=True))

    op.create_table(
        "users",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),             # admin | analyst | viewer
        sa.Column("district", sa.Text(), nullable=True),          # viewer scoping
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.create_table(
        "sessions",
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("token"),
    )
    op.create_table(
        "deliveries",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("report_id", sa.Text(), nullable=False),
        sa.Column("recipient", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),           # sent | failed
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("deliveries")
    op.drop_table("sessions")
    op.drop_table("users")
    op.drop_column("conversations", "user_id")
    op.drop_column("runs", "user_id")
    op.drop_column("datasets", "district")
