"""
Core data models for SSR Studio.

Defines the canonical schemas for environments, artifacts, episodes,
validation reports, and solver attempts as described in the PRD.
"""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================

class LanguageHint(str, Enum):
    """Programming language hints for environments."""
    UNKNOWN = "unknown"
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    GO = "go"
    RUST = "rust"
    JAVA = "java"
    CPP = "cpp"


class InjectionStrategy(str, Enum):
    """Bug injection strategy modes (SSR paper §3.4)."""
    DIRECT = "direct"
    REMOVAL_ONLY = "removal_only"
    HISTORY_AWARE = "history_aware"


class EpisodeStatus(str, Enum):
    """Episode execution status."""
    PENDING = "pending"
    INJECTING = "injecting"
    VALIDATING = "validating"
    SOLVING = "solving"
    EVALUATING = "evaluating"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ValidationStepName(str, Enum):
    """Validation step names (SSR paper §2.3, Fig. 4)."""
    TEST_FILES_EXISTENCE = "test_files_existence"
    PARSER_VALIDITY = "parser_validity"
    ORIGINAL_TESTS_PASS = "original_tests_pass"
    BUG_SCOPE = "bug_scope"
    BUG_VALIDITY = "bug_validity"
    TEST_WEAKENING_VALIDITY = "test_weakening_validity"
    INVERSE_MUTATION_TESTING = "inverse_mutation_testing"


class TestStatus(str, Enum):
    """Individual test status."""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


# =============================================================================
# Environment Models
# =============================================================================

class EnvironmentCreate(BaseModel):
    """Request model for creating an environment."""
    name: str = Field(..., min_length=1, max_length=255)
    docker_image_ref: str = Field(..., description="Docker image reference (local or registry)")
    language_hint: LanguageHint = LanguageHint.UNKNOWN
    notes: str | None = None


class Environment(BaseModel):
    """Environment model (SSR Studio PRD §9.1)."""
    env_id: UUID = Field(default_factory=uuid4)
    name: str
    docker_image_ref: str
    docker_image_digest: str | None = None
    language_hint: LanguageHint = LanguageHint.UNKNOWN
    created_at: datetime = Field(default_factory=datetime.utcnow)
    notes: str | None = None
    
    class Config:
        from_attributes = True


# =============================================================================
# Bug Artifact Models
# =============================================================================

class ArtifactMetadata(BaseModel):
    """Metadata for a bug artifact (SSR paper §2.3)."""
    artifact_id: UUID = Field(default_factory=uuid4)
    env_id: UUID
    injection_strategy: InjectionStrategy
    min_passing_tests: int
    min_changed_files: int
    min_failing_tests: int
    max_test_runtime_sec: int
    created_by_model: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


class BugArtifact(BaseModel):
    """
    Complete bug artifact bundle (SSR paper §2.3).
    
    Contains the five required files:
    - test_script.sh
    - test_files.txt
    - test_parser.py
    - bug_inject.diff
    - test_weaken.diff
    """
    metadata: ArtifactMetadata
    test_script: str = Field(..., description="Contents of test_script.sh")
    test_files: list[str] = Field(..., description="List of test file paths")
    test_parser: str = Field(..., description="Contents of test_parser.py")
    bug_inject_diff: str = Field(..., description="Code-only patch introducing the bug")
    test_weaken_diff: str = Field(..., description="Tests-only patch to hide the bug")
    
    # Optional: for higher-order bugs
    parent_artifact_id: UUID | None = None
    bug_order: int = 1


# =============================================================================
# Validation Models
# =============================================================================

class ValidationStepResult(BaseModel):
    """Result of a single validation step."""
    name: ValidationStepName
    passed: bool
    details: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    duration_ms: int = 0


class ValidationReport(BaseModel):
    """
    Complete validation report (SSR paper §2.3, Fig. 4).
    
    Implements all SSR consistency checks including inverse mutation testing.
    """
    artifact_id: UUID
    valid: bool
    steps: list[ValidationStepResult]
    total_duration_ms: int = 0
    logs_ref: str | None = None  # Reference to full logs in artifact store
    created_at: datetime = Field(default_factory=datetime.utcnow)


# =============================================================================
# Solver & Evaluation Models
# =============================================================================

class ToolCall(BaseModel):
    """Record of a single tool call by the agent."""
    timestamp: datetime
    tool_name: str
    arguments: dict[str, Any]
    result: dict[str, Any]
    duration_ms: int
    truncated: bool = False


class SolverAttempt(BaseModel):
    """
    Single solver attempt and its evaluation (SSR paper §2.4).
    """
    attempt_id: UUID = Field(default_factory=uuid4)
    artifact_id: UUID
    attempt_number: int
    
    # Inputs
    oracle_test_patch: str = Field(..., description="Reversed test_weaken.diff")
    
    # Outputs
    pred_patch: str | None = None  # The predicted fix patch
    success: bool = False
    
    # Test results
    test_summary: dict[str, int] = Field(
        default_factory=lambda: {"passed": 0, "failed": 0, "skipped": 0, "error": 0}
    )
    per_test_status: dict[str, TestStatus] = Field(default_factory=dict)
    
    # Execution details
    tool_calls: list[ToolCall] = Field(default_factory=list)
    total_tool_steps: int = 0
    total_tokens_used: int = 0
    duration_ms: int = 0
    
    # Storage references
    pred_patch_ref: str | None = None
    tool_trace_ref: str | None = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)


class EvaluationReport(BaseModel):
    """
    Evaluation report for a solver attempt (SSR paper §2.4, Fig. 7).
    
    Implements test restoration to prevent "fixing by editing tests".
    """
    attempt_id: UUID
    success: bool
    
    # Test counts
    tests_passed: int = 0
    tests_failed: int = 0
    tests_total: int = 0
    
    # Per-test status
    per_test_status: dict[str, TestStatus] = Field(default_factory=dict)
    
    # Restoration info
    test_files_restored: list[str] = Field(default_factory=list)
    
    # Timing and logs
    duration_ms: int = 0
    logs_ref: str | None = None


# =============================================================================
# Episode Models
# =============================================================================

class EpisodeConfig(BaseModel):
    """Configuration for running an episode."""
    injection_strategy: InjectionStrategy = InjectionStrategy.REMOVAL_ONLY
    min_passing_tests: int = 10
    min_changed_files: int = 1
    min_failing_tests: int = 1
    max_test_runtime_sec: int = 90
    solver_attempts: int = 4
    reward_alpha: float = 0.8
    enable_higher_order: bool = False
    model_id: str | None = None
    random_seed: int | None = None


class EpisodeCreate(BaseModel):
    """Request model for creating an episode."""
    env_id: UUID
    config: EpisodeConfig = Field(default_factory=EpisodeConfig)


class Episode(BaseModel):
    """
    Complete episode rollup (SSR paper PRD §9.5).
    
    Tracks the full lifecycle: injection → validation → solve → evaluation.
    """
    episode_id: UUID = Field(default_factory=uuid4)
    env_id: UUID
    
    # Status tracking
    status: EpisodeStatus = EpisodeStatus.PENDING
    error_message: str | None = None
    
    # Configuration
    config: EpisodeConfig
    
    # Artifact (set after successful injection)
    artifact_id: UUID | None = None
    artifact: BugArtifact | None = None
    
    # Validation (set after validation completes)
    validation_report: ValidationReport | None = None
    
    # Solver attempts (populated during solving phase)
    solver_attempts: list[SolverAttempt] = Field(default_factory=list)
    
    # Aggregate metrics (computed after all attempts complete)
    solve_rate: float | None = None  # s = successes / N
    
    # Rewards (SSR paper Eq. (1) and (2))
    r_inject: float | None = None
    r_solve_avg: float | None = None
    
    # Metadata
    model_version: str | None = None
    container_image_digest: str | None = None
    random_seed: int | None = None
    
    # Timing
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    
    class Config:
        from_attributes = True


class EpisodeSummary(BaseModel):
    """Lightweight episode summary for listing."""
    episode_id: UUID
    env_id: UUID
    env_name: str | None = None
    status: EpisodeStatus
    injection_strategy: InjectionStrategy
    artifact_valid: bool | None = None
    solve_rate: float | None = None
    r_inject: float | None = None
    created_at: datetime


# =============================================================================
# Metrics Models
# =============================================================================

class EpisodeMetrics(BaseModel):
    """Aggregated metrics across episodes."""
    total_episodes: int = 0
    completed_episodes: int = 0
    failed_episodes: int = 0
    
    # Artifact metrics
    valid_artifacts: int = 0
    artifact_validity_rate: float = 0.0
    validation_failure_breakdown: dict[str, int] = Field(default_factory=dict)
    
    # Solver metrics
    total_solve_attempts: int = 0
    successful_solves: int = 0
    overall_solve_rate: float = 0.0
    solve_rate_distribution: list[float] = Field(default_factory=list)
    
    # Reward metrics
    avg_r_inject: float = 0.0
    avg_r_solve: float = 0.0
    reward_distribution: dict[str, list[float]] = Field(default_factory=dict)
    
    # Performance metrics
    avg_tests_discovered: float = 0.0
    avg_test_runtime_sec: float = 0.0
    avg_changed_files: float = 0.0
    avg_failing_tests: float = 0.0


# =============================================================================
# Training Models (P2 Feature)
# =============================================================================

class TrainingRun(BaseModel):
    """Training run configuration and status."""
    run_id: UUID = Field(default_factory=uuid4)
    base_model: str
    lora_config: dict[str, Any]
    
    # Progress
    current_step: int = 0
    total_steps: int = 0
    
    # Metrics over time
    solve_rate_history: list[float] = Field(default_factory=list)
    validity_rate_history: list[float] = Field(default_factory=list)
    reward_history: list[dict[str, float]] = Field(default_factory=list)
    
    # Checkpoints
    checkpoint_refs: list[str] = Field(default_factory=list)
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "pending"
