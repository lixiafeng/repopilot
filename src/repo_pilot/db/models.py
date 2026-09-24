from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from repo_pilot.db.base import Base


class RepairTask(Base):
    __tablename__ = "repair_tasks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    repo_path: Mapped[str] = mapped_column(Text, nullable=False)
    workspace_path: Mapped[str | None] = mapped_column(
    Text,
    nullable=True,
)
    issue: Mapped[str] = mapped_column(Text, nullable=False)
    test_command: Mapped[str] = mapped_column(Text, nullable=False)

    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="fake")
    model: Mapped[str] = mapped_column(String(128), nullable=False, default="fake-model")
    max_iterations: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    apply_patch: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    command_timeout_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=120)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    current_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    current_iteration: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    success: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_diff: Mapped[str | None] = mapped_column(Text, nullable=True)
    test_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    attempts: Mapped[list["RepairAttempt"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="RepairAttempt.attempt_no",
    )
    trace_events: Mapped[list["TraceEvent"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="TraceEvent.id",
    )


class RepairAttempt(Base):
    __tablename__ = "repair_attempts"
    __table_args__ = (
        UniqueConstraint("task_id", "attempt_no", name="uq_attempt_task_no"),
        Index("ix_attempt_task_id", "task_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("repair_tasks.id", ondelete="CASCADE"), nullable=False
    )
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="RUNNING")
    stage: Mapped[str | None] = mapped_column(String(64), nullable=True)

    plan: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSON, nullable=True)
    patch: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSON, nullable=True)
    diff: Mapped[str | None] = mapped_column(Text, nullable=True)
    test_output: Mapped[str | None] = mapped_column(Text, nullable=True)

    error_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    task: Mapped[RepairTask] = relationship(back_populates="attempts")
    trace_events: Mapped[list["TraceEvent"]] = relationship(
        back_populates="attempt",
        passive_deletes=True,
    )


class TraceEvent(Base):
    __tablename__ = "trace_events"
    __table_args__ = (
        Index("ix_trace_task_id", "task_id"),
        Index("ix_trace_attempt_id", "attempt_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey("repair_tasks.id", ondelete="CASCADE"), nullable=False
    )
    attempt_id: Mapped[int | None] = mapped_column(
        ForeignKey("repair_attempts.id", ondelete="SET NULL"), nullable=True
    )

    stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    task: Mapped[RepairTask] = relationship(back_populates="trace_events")
    attempt: Mapped[RepairAttempt | None] = relationship(back_populates="trace_events")
