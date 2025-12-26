"""
Database models and session management for SSR Studio.

Uses SQLAlchemy async with PostgreSQL.
"""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from ssr_studio.config import settings
from ssr_studio.models import EpisodeStatus, InjectionStrategy, LanguageHint, ValidationStepName


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


# =============================================================================
# Database Engine and Session
# =============================================================================

engine = create_async_engine(
    settings.database_url,
    pool_size=settings.database_pool_size,
    max_overflow=settings.database_max_overflow,
    echo=settings.debug,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncSession:
    """Get a database session for dependency injection."""
    async with async_session_factory() as session:
        yield session


async def init_db():
    """Initialize the database schema."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# =============================================================================
# Database Models
# =============================================================================

class EnvironmentDB(Base):
    """Database model for environments."""
    
    __tablename__ = "environments"
    
    env_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    docker_image_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    docker_image_digest: Mapped[str | None] = mapped_column(String(128), nullable=True)
    language_hint: Mapped[str] = mapped_column(
        String(32), default=LanguageHint.UNKNOWN.value
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    episodes: Mapped[list["EpisodeDB"]] = relationship(back_populates="environment")


class ArtifactDB(Base):
    """Database model for bug artifacts."""
    
    __tablename__ = "artifacts"
    
    artifact_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    env_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("environments.env_id"))
    
    # Injection configuration
    injection_strategy: Mapped[str] = mapped_column(String(32), nullable=False)
    min_passing_tests: Mapped[int] = mapped_column(Integer, default=10)
    min_changed_files: Mapped[int] = mapped_column(Integer, default=1)
    min_failing_tests: Mapped[int] = mapped_column(Integer, default=1)
    max_test_runtime_sec: Mapped[int] = mapped_column(Integer, default=90)
    
    # Model info
    created_by_model: Mapped[str] = mapped_column(String(128), nullable=False)
    
    # Artifact content (stored as references to object storage)
    test_script_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    test_files_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    test_parser_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    bug_inject_diff_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    test_weaken_diff_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    
    # Higher-order bug support
    parent_artifact_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("artifacts.artifact_id"), nullable=True
    )
    bug_order: Mapped[int] = mapped_column(Integer, default=1)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    episode: Mapped["EpisodeDB"] = relationship(back_populates="artifact")


class ValidationReportDB(Base):
    """Database model for validation reports."""
    
    __tablename__ = "validation_reports"
    
    report_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    artifact_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    
    valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    steps: Mapped[dict] = mapped_column(JSON, nullable=False)  # List of validation step results
    total_duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    logs_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationship
    episode: Mapped["EpisodeDB"] = relationship(back_populates="validation_report")


class SolverAttemptDB(Base):
    """Database model for solver attempts."""
    
    __tablename__ = "solver_attempts"
    
    attempt_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    episode_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("episodes.episode_id"))
    artifact_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Results
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    test_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    
    # Execution details
    total_tool_steps: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    
    # Storage references
    pred_patch_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    tool_trace_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    evaluation_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # Relationships
    episode: Mapped["EpisodeDB"] = relationship(back_populates="solver_attempts")


class EpisodeDB(Base):
    """Database model for episodes."""
    
    __tablename__ = "episodes"
    
    episode_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    env_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("environments.env_id"))
    
    # Status
    status: Mapped[str] = mapped_column(String(32), default=EpisodeStatus.PENDING.value, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Configuration
    config: Mapped[dict] = mapped_column(JSON, nullable=False)
    
    # Artifact reference
    artifact_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("artifacts.artifact_id"), nullable=True
    )
    
    # Validation report reference
    validation_report_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("validation_reports.report_id"), nullable=True
    )
    
    # Aggregate metrics
    solve_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    r_inject: Mapped[float | None] = mapped_column(Float, nullable=True)
    r_solve_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    
    # Metadata
    model_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    container_image_digest: Mapped[str | None] = mapped_column(String(128), nullable=True)
    random_seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    
    # Timing
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    
    # Relationships
    environment: Mapped["EnvironmentDB"] = relationship(back_populates="episodes")
    artifact: Mapped["ArtifactDB | None"] = relationship(back_populates="episode")
    validation_report: Mapped["ValidationReportDB | None"] = relationship(back_populates="episode")
    solver_attempts: Mapped[list["SolverAttemptDB"]] = relationship(back_populates="episode")


class TrainingRunDB(Base):
    """Database model for training runs (P2 feature)."""
    
    __tablename__ = "training_runs"
    
    run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    base_model: Mapped[str] = mapped_column(String(256), nullable=False)
    lora_config: Mapped[dict] = mapped_column(JSON, nullable=False)
    
    # Progress
    current_step: Mapped[int] = mapped_column(Integer, default=0)
    total_steps: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    
    # Metrics over time (stored as JSON arrays)
    metrics_history: Mapped[dict] = mapped_column(JSON, default=dict)
    
    # Checkpoints
    checkpoint_refs: Mapped[list] = mapped_column(JSON, default=list)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
