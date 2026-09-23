"""create repair task tables

Revision ID: 0001
Revises:
Create Date: 2026-09-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "repair_tasks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("repo_path", sa.Text(), nullable=False),
        sa.Column("issue", sa.Text(), nullable=False),
        sa.Column("test_command", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("max_iterations", sa.Integer(), nullable=False),
        sa.Column("apply_patch", sa.Boolean(), nullable=False),
        sa.Column("command_timeout_sec", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_stage", sa.String(length=64), nullable=True),
        sa.Column("current_iteration", sa.Integer(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("final_diff", sa.Text(), nullable=True),
        sa.Column("test_output", sa.Text(), nullable=True),
        sa.Column("error_type", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "repair_attempts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("stage", sa.String(length=64), nullable=True),
        sa.Column("plan", sa.JSON(), nullable=True),
        sa.Column("patch", sa.JSON(), nullable=True),
        sa.Column("diff", sa.Text(), nullable=True),
        sa.Column("test_output", sa.Text(), nullable=True),
        sa.Column("error_type", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["repair_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_id", "attempt_no", name="uq_attempt_task_no"),
    )
    op.create_index("ix_attempt_task_id", "repair_attempts", ["task_id"], unique=False)

    op.create_table(
        "trace_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("attempt_id", sa.BigInteger(), nullable=True),
        sa.Column("stage", sa.String(length=64), nullable=True),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["attempt_id"], ["repair_attempts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["repair_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trace_attempt_id", "trace_events", ["attempt_id"], unique=False)
    op.create_index("ix_trace_task_id", "trace_events", ["task_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_trace_task_id", table_name="trace_events")
    op.drop_index("ix_trace_attempt_id", table_name="trace_events")
    op.drop_table("trace_events")
    op.drop_index("ix_attempt_task_id", table_name="repair_attempts")
    op.drop_table("repair_attempts")
    op.drop_table("repair_tasks")
