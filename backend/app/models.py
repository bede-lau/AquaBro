"""ORM models.

Mirrors §5 of the spec. Adds ``agent_events`` — an append-only audit log of
every agent decision/action, which is the concrete proof of the
"deterministic + auditable" pitch.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class TelemetryLog(Base):
    __tablename__ = "telemetry_logs"

    id: Mapped[uuid.UUID] = _pk()
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    tank_id: Mapped[str] = mapped_column(String(32), default="TANK-01", index=True)
    do_level: Mapped[float] = mapped_column(Float)        # mg/L
    ph_level: Mapped[float] = mapped_column(Float)
    temp_c: Mapped[float] = mapped_column(Float)
    # True when a chaos injection overrode the value — distinguishes
    # simulated fault injection from organic drift in the audit trail.
    is_override: Mapped[bool] = mapped_column(Boolean, default=False)


class AutoFeedLog(Base):
    __tablename__ = "auto_feed_logs"

    id: Mapped[uuid.UUID] = _pk()
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    mass_grams: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(24))  # "DISPENSED" | "LOCKED_BY_AI"
    rate_pct: Mapped[float] = mapped_column(Float, default=100.0)


class AgentEvent(Base):
    """Append-only audit log of the reasoning loop.

    One row per agent step: which agent, what it concluded, what payload it
    emitted. This is what makes the system's behaviour reproducible and
    explainable — queryable after any incident.
    """

    __tablename__ = "agent_events"

    id: Mapped[uuid.UUID] = _pk()
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    agent: Mapped[str] = mapped_column(String(32), index=True)
    # TELEMETRY | VISION | CONTEXT | CAUSAL | ACTION | ORCHESTRATOR
    level: Mapped[str] = mapped_column(String(16), default="INFO")
    message: Mapped[str] = mapped_column(String)
    # Structured detail (JSON-encoded) for the payload/intent.
    detail: Mapped[str | None] = mapped_column(String, nullable=True)
