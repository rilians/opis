from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base, utcnow


class Endpoint(Base):
    __tablename__ = "endpoints"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    method: Mapped[str] = mapped_column(String(4), default="GET", nullable=False)
    expected_status: Mapped[int] = mapped_column(Integer, default=200, nullable=False)
    interval_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    failure_threshold: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    recovery_threshold: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_checked_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    next_check_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    last_is_up: Mapped[bool | None] = mapped_column(Boolean)
    last_status_code: Mapped[int | None] = mapped_column(Integer)
    last_response_ms: Mapped[float | None] = mapped_column(Float)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    consecutive_successes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failure_started_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))

    checks: Mapped[list["Check"]] = relationship(back_populates="endpoint", cascade="all, delete-orphan", passive_deletes=True)
    incidents: Mapped[list["Incident"]] = relationship(back_populates="endpoint", cascade="all, delete-orphan", passive_deletes=True)


class Check(Base):
    __tablename__ = "checks"
    __table_args__ = (Index("ix_checks_endpoint_time", "endpoint_id", "checked_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    endpoint_id: Mapped[int] = mapped_column(ForeignKey("endpoints.id", ondelete="CASCADE"), nullable=False, index=True)
    checked_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    is_up: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer)
    response_ms: Mapped[float | None] = mapped_column(Float)
    error_type: Mapped[str | None] = mapped_column(String(40))
    error_message: Mapped[str | None] = mapped_column(String(500))
    endpoint: Mapped["Endpoint"] = relationship(back_populates="checks")


class Incident(Base):
    __tablename__ = "incidents"
    __table_args__ = (Index("ix_incidents_endpoint_open", "endpoint_id", "ended_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    endpoint_id: Mapped[int] = mapped_column(ForeignKey("endpoints.id", ondelete="CASCADE"), nullable=False, index=True)
    endpoint_name: Mapped[str] = mapped_column(String(80), nullable=False)
    endpoint_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    method: Mapped[str] = mapped_column(String(4), nullable=False)
    expected_status: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    detected_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    end_reason: Mapped[str | None] = mapped_column(String(24))  # recovered, archived, config_changed
    first_error_type: Mapped[str | None] = mapped_column(String(40))
    first_error_message: Mapped[str | None] = mapped_column(String(500))
    first_status_code: Mapped[int | None] = mapped_column(Integer)
    last_error_type: Mapped[str | None] = mapped_column(String(40))
    last_error_message: Mapped[str | None] = mapped_column(String(500))
    last_status_code: Mapped[int | None] = mapped_column(Integer)
    failure_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    endpoint: Mapped["Endpoint"] = relationship(back_populates="incidents")


class AppConfig(Base):
    __tablename__ = "app_config"
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    sla_target: Mapped[float] = mapped_column(Float, default=99.9, nullable=False)
    webhook_url: Mapped[str | None] = mapped_column(String(2048))
    demo_seeded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class AlertDelivery(Base):
    __tablename__ = "alert_deliveries"
    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int | None] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    endpoint_id: Mapped[int | None] = mapped_column(ForeignKey("endpoints.id", ondelete="CASCADE"))
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(String(500))
