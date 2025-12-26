"""
FastAPI application and API routes for SSR Studio.
"""

from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException, Depends, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from ssr_studio import __version__
from ssr_studio.config import settings, ui_config
from ssr_studio.database import (
    get_db_session,
    init_db,
    EnvironmentDB,
    EpisodeDB,
    ArtifactDB,
    SolverAttemptDB,
    ValidationReportDB,
)
from ssr_studio.models import (
    Environment,
    EnvironmentCreate,
    Episode,
    EpisodeCreate,
    EpisodeSummary,
    EpisodeStatus,
    EpisodeMetrics,
    BugArtifact,
    ValidationReport,
    SolverAttempt,
    InjectionStrategy,
)
from ssr_studio.storage import get_storage
from ssr_studio.orchestrator import EpisodeOrchestrator


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    await init_db()
    yield
    # Shutdown


app = FastAPI(
    title="SSR Studio",
    description="Self-Play SWE-RL Demo & Research Platform",
    version=__version__,
    lifespan=lifespan,
)

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Health Check
# =============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": __version__}


@app.get("/api/v1/config")
async def get_config():
    """Get public configuration."""
    return {
        "app_name": settings.app_name,
        "demo_mode": ui_config.demo_mode,
        "default_injection_strategy": settings.injection_strategy.value,
        "default_solver_attempts": settings.solver_attempts_per_bug,
        "model_provider": settings.model_provider,
    }


# =============================================================================
# Environments API
# =============================================================================

@app.get("/api/v1/environments", response_model=list[Environment])
async def list_environments(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
):
    """List all registered environments."""
    result = await db.execute(
        select(EnvironmentDB)
        .order_by(EnvironmentDB.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    environments = result.scalars().all()
    return [Environment.model_validate(env) for env in environments]


@app.get("/api/v1/environments/{env_id}", response_model=Environment)
async def get_environment(
    env_id: UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """Get a specific environment by ID."""
    result = await db.execute(
        select(EnvironmentDB).where(EnvironmentDB.env_id == env_id)
    )
    env = result.scalar_one_or_none()
    if not env:
        raise HTTPException(status_code=404, detail="Environment not found")
    return Environment.model_validate(env)


@app.post("/api/v1/environments", response_model=Environment, status_code=201)
async def create_environment(
    env_create: EnvironmentCreate,
    db: AsyncSession = Depends(get_db_session),
):
    """Register a new environment from a Docker image reference."""
    # TODO: Validate Docker image exists and is pullable
    # TODO: Extract image digest
    
    env_db = EnvironmentDB(
        name=env_create.name,
        docker_image_ref=env_create.docker_image_ref,
        language_hint=env_create.language_hint.value,
        notes=env_create.notes,
    )
    db.add(env_db)
    await db.commit()
    await db.refresh(env_db)
    
    return Environment.model_validate(env_db)


@app.delete("/api/v1/environments/{env_id}", status_code=204)
async def delete_environment(
    env_id: UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """Delete an environment."""
    result = await db.execute(
        select(EnvironmentDB).where(EnvironmentDB.env_id == env_id)
    )
    env = result.scalar_one_or_none()
    if not env:
        raise HTTPException(status_code=404, detail="Environment not found")
    
    await db.delete(env)
    await db.commit()


# =============================================================================
# Episodes API
# =============================================================================

@app.get("/api/v1/episodes", response_model=list[EpisodeSummary])
async def list_episodes(
    env_id: UUID | None = None,
    status: EpisodeStatus | None = None,
    strategy: InjectionStrategy | None = None,
    valid_only: bool = False,
    solved_only: bool = False,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
):
    """List episodes with optional filters."""
    query = select(EpisodeDB).options(selectinload(EpisodeDB.environment))
    
    if env_id:
        query = query.where(EpisodeDB.env_id == env_id)
    if status:
        query = query.where(EpisodeDB.status == status.value)
    if valid_only:
        query = query.where(EpisodeDB.artifact_id.isnot(None))
    if solved_only:
        query = query.where(EpisodeDB.solve_rate > 0)
    
    query = query.order_by(EpisodeDB.created_at.desc()).offset(skip).limit(limit)
    
    result = await db.execute(query)
    episodes = result.scalars().all()
    
    summaries = []
    for ep in episodes:
        config = ep.config or {}
        summaries.append(EpisodeSummary(
            episode_id=ep.episode_id,
            env_id=ep.env_id,
            env_name=ep.environment.name if ep.environment else None,
            status=EpisodeStatus(ep.status),
            injection_strategy=InjectionStrategy(config.get("injection_strategy", "removal_only")),
            artifact_valid=ep.artifact_id is not None,
            solve_rate=ep.solve_rate,
            r_inject=ep.r_inject,
            created_at=ep.created_at,
        ))
    
    return summaries


@app.get("/api/v1/episodes/{episode_id}", response_model=Episode)
async def get_episode(
    episode_id: UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """Get detailed episode information."""
    result = await db.execute(
        select(EpisodeDB)
        .options(
            selectinload(EpisodeDB.environment),
            selectinload(EpisodeDB.artifact),
            selectinload(EpisodeDB.validation_report),
            selectinload(EpisodeDB.solver_attempts),
        )
        .where(EpisodeDB.episode_id == episode_id)
    )
    episode = result.scalar_one_or_none()
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    
    # Build full Episode model with nested data
    return await _build_episode_response(episode, db)


@app.post("/api/v1/episodes", response_model=Episode, status_code=201)
async def create_episode(
    episode_create: EpisodeCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db_session),
):
    """Create and start a new self-play episode."""
    # Verify environment exists
    result = await db.execute(
        select(EnvironmentDB).where(EnvironmentDB.env_id == episode_create.env_id)
    )
    env = result.scalar_one_or_none()
    if not env:
        raise HTTPException(status_code=404, detail="Environment not found")
    
    # Create episode record
    episode_db = EpisodeDB(
        env_id=episode_create.env_id,
        config=episode_create.config.model_dump(),
        status=EpisodeStatus.PENDING.value,
    )
    db.add(episode_db)
    await db.commit()
    await db.refresh(episode_db)
    
    # Start episode execution in background
    background_tasks.add_task(
        run_episode_task,
        episode_id=episode_db.episode_id,
    )
    
    return await _build_episode_response(episode_db, db)


@app.post("/api/v1/episodes/{episode_id}/cancel", status_code=200)
async def cancel_episode(
    episode_id: UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """Cancel a running episode."""
    result = await db.execute(
        select(EpisodeDB).where(EpisodeDB.episode_id == episode_id)
    )
    episode = result.scalar_one_or_none()
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    
    if episode.status in [EpisodeStatus.COMPLETE.value, EpisodeStatus.FAILED.value]:
        raise HTTPException(status_code=400, detail="Episode already finished")
    
    episode.status = EpisodeStatus.CANCELLED.value
    await db.commit()
    
    return {"status": "cancelled"}


# =============================================================================
# Artifacts API
# =============================================================================

@app.get("/api/v1/episodes/{episode_id}/artifact")
async def get_episode_artifact(
    episode_id: UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """Get the bug artifact for an episode."""
    result = await db.execute(
        select(EpisodeDB)
        .options(selectinload(EpisodeDB.artifact))
        .where(EpisodeDB.episode_id == episode_id)
    )
    episode = result.scalar_one_or_none()
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    if not episode.artifact:
        raise HTTPException(status_code=404, detail="No artifact for this episode")
    
    storage = get_storage()
    artifact = episode.artifact
    
    return {
        "artifact_id": str(artifact.artifact_id),
        "test_script": await storage.read(artifact.test_script_ref),
        "test_files": (await storage.read(artifact.test_files_ref)).split("\n"),
        "test_parser": await storage.read(artifact.test_parser_ref),
        "bug_inject_diff": await storage.read(artifact.bug_inject_diff_ref),
        "test_weaken_diff": await storage.read(artifact.test_weaken_diff_ref),
        "metadata": {
            "injection_strategy": artifact.injection_strategy,
            "bug_order": artifact.bug_order,
            "created_at": artifact.created_at.isoformat(),
        }
    }


@app.get("/api/v1/episodes/{episode_id}/artifact/download")
async def download_artifact_bundle(
    episode_id: UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """Download the artifact bundle as a tarball."""
    result = await db.execute(
        select(EpisodeDB)
        .options(selectinload(EpisodeDB.artifact))
        .where(EpisodeDB.episode_id == episode_id)
    )
    episode = result.scalar_one_or_none()
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    if not episode.artifact:
        raise HTTPException(status_code=404, detail="No artifact for this episode")
    
    storage = get_storage()
    tarball = await storage.get_artifact_tarball(episode.artifact.artifact_id)
    
    return StreamingResponse(
        tarball,
        media_type="application/x-tar",
        headers={"Content-Disposition": f"attachment; filename=artifact_{episode.artifact.artifact_id}.tar.gz"}
    )


# =============================================================================
# Validation & Solver Attempts API
# =============================================================================

@app.get("/api/v1/episodes/{episode_id}/validation")
async def get_validation_report(
    episode_id: UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """Get the validation report for an episode."""
    result = await db.execute(
        select(EpisodeDB)
        .options(selectinload(EpisodeDB.validation_report))
        .where(EpisodeDB.episode_id == episode_id)
    )
    episode = result.scalar_one_or_none()
    if not episode:
        raise HTTPException(status_code=404, detail="Episode not found")
    if not episode.validation_report:
        raise HTTPException(status_code=404, detail="No validation report for this episode")
    
    report = episode.validation_report
    return {
        "artifact_id": str(report.artifact_id),
        "valid": report.valid,
        "steps": report.steps,
        "total_duration_ms": report.total_duration_ms,
        "created_at": report.created_at.isoformat(),
    }


@app.get("/api/v1/episodes/{episode_id}/attempts", response_model=list[SolverAttempt])
async def get_solver_attempts(
    episode_id: UUID,
    db: AsyncSession = Depends(get_db_session),
):
    """Get all solver attempts for an episode."""
    result = await db.execute(
        select(SolverAttemptDB)
        .where(SolverAttemptDB.episode_id == episode_id)
        .order_by(SolverAttemptDB.attempt_number)
    )
    attempts = result.scalars().all()
    
    storage = get_storage()
    response = []
    for attempt in attempts:
        pred_patch = None
        if attempt.pred_patch_ref:
            pred_patch = await storage.read(attempt.pred_patch_ref)
        
        response.append(SolverAttempt(
            attempt_id=attempt.attempt_id,
            artifact_id=attempt.artifact_id,
            attempt_number=attempt.attempt_number,
            oracle_test_patch="",  # Loaded on demand
            pred_patch=pred_patch,
            success=attempt.success,
            test_summary=attempt.test_summary,
            total_tool_steps=attempt.total_tool_steps,
            total_tokens_used=attempt.total_tokens_used,
            duration_ms=attempt.duration_ms,
            created_at=attempt.created_at,
        ))
    
    return response


# =============================================================================
# Metrics API
# =============================================================================

@app.get("/api/v1/metrics", response_model=EpisodeMetrics)
async def get_metrics(
    env_id: UUID | None = None,
    db: AsyncSession = Depends(get_db_session),
):
    """Get aggregated metrics across episodes."""
    query = select(EpisodeDB)
    if env_id:
        query = query.where(EpisodeDB.env_id == env_id)
    
    result = await db.execute(query)
    episodes = result.scalars().all()
    
    metrics = EpisodeMetrics()
    metrics.total_episodes = len(episodes)
    
    for ep in episodes:
        if ep.status == EpisodeStatus.COMPLETE.value:
            metrics.completed_episodes += 1
        elif ep.status == EpisodeStatus.FAILED.value:
            metrics.failed_episodes += 1
        
        if ep.artifact_id:
            metrics.valid_artifacts += 1
        
        if ep.solve_rate is not None:
            metrics.solve_rate_distribution.append(ep.solve_rate)
        
        if ep.r_inject is not None:
            if "r_inject" not in metrics.reward_distribution:
                metrics.reward_distribution["r_inject"] = []
            metrics.reward_distribution["r_inject"].append(ep.r_inject)
        
        if ep.r_solve_avg is not None:
            if "r_solve" not in metrics.reward_distribution:
                metrics.reward_distribution["r_solve"] = []
            metrics.reward_distribution["r_solve"].append(ep.r_solve_avg)
    
    if metrics.total_episodes > 0:
        metrics.artifact_validity_rate = metrics.valid_artifacts / metrics.total_episodes
    
    if metrics.solve_rate_distribution:
        metrics.overall_solve_rate = sum(metrics.solve_rate_distribution) / len(metrics.solve_rate_distribution)
    
    if metrics.reward_distribution.get("r_inject"):
        metrics.avg_r_inject = sum(metrics.reward_distribution["r_inject"]) / len(metrics.reward_distribution["r_inject"])
    
    if metrics.reward_distribution.get("r_solve"):
        metrics.avg_r_solve = sum(metrics.reward_distribution["r_solve"]) / len(metrics.reward_distribution["r_solve"])
    
    return metrics


# =============================================================================
# Helper Functions
# =============================================================================

async def _build_episode_response(episode_db: EpisodeDB, db: AsyncSession) -> Episode:
    """Build a full Episode response from database model."""
    from ssr_studio.models import EpisodeConfig
    
    config = EpisodeConfig(**episode_db.config) if episode_db.config else EpisodeConfig()
    
    return Episode(
        episode_id=episode_db.episode_id,
        env_id=episode_db.env_id,
        status=EpisodeStatus(episode_db.status),
        error_message=episode_db.error_message,
        config=config,
        artifact_id=episode_db.artifact_id,
        solve_rate=episode_db.solve_rate,
        r_inject=episode_db.r_inject,
        r_solve_avg=episode_db.r_solve_avg,
        model_version=episode_db.model_version,
        container_image_digest=episode_db.container_image_digest,
        random_seed=episode_db.random_seed,
        created_at=episode_db.created_at,
        started_at=episode_db.started_at,
        completed_at=episode_db.completed_at,
    )


async def run_episode_task(episode_id: UUID):
    """Background task to run an episode."""
    from ssr_studio.database import async_session_factory
    
    async with async_session_factory() as db:
        orchestrator = EpisodeOrchestrator(db)
        await orchestrator.run_episode(episode_id)
