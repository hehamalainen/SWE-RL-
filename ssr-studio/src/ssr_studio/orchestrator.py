"""
Episode Orchestrator for SSR Studio.

Manages the full SSR self-play pipeline:
INJECT → VALIDATE → SOLVE(N) → EVALUATE → COMPLETE

Implements the episode execution sequence from PRD §8.2.
"""

import json
from datetime import datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ssr_studio.config import settings, InjectionStrategy
from ssr_studio.database import (
    EpisodeDB,
    EnvironmentDB,
    ArtifactDB,
    ValidationReportDB,
    SolverAttemptDB,
)
from ssr_studio.models import (
    EpisodeStatus,
    EpisodeConfig,
    BugArtifact,
    ArtifactMetadata,
    ValidationReport,
    SolverAttempt,
    EvaluationReport,
    TestStatus,
)
from ssr_studio.sandbox import Sandbox
from ssr_studio.storage import get_storage
from ssr_studio.validator import Validator
from ssr_studio.agents import InjectorAgent, SolverAgent

logger = structlog.get_logger()


class EpisodeOrchestrator:
    """
    Orchestrates the full SSR episode lifecycle.
    
    An episode consists of:
    1. Start container from repo image
    2. Run injector agent to produce artifact
    3. Validate the artifact
    4. If valid, run N solver attempts
    5. Evaluate each attempt
    6. Compute solve rate and rewards
    7. Persist everything
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.storage = get_storage()
    
    async def run_episode(self, episode_id: UUID) -> None:
        """
        Run a complete episode.
        
        This is the main entry point called by the background task.
        """
        logger.info("Starting episode", episode_id=str(episode_id))
        
        try:
            # Load episode
            result = await self.db.execute(
                select(EpisodeDB)
                .options(selectinload(EpisodeDB.environment))
                .where(EpisodeDB.episode_id == episode_id)
            )
            episode = result.scalar_one_or_none()
            
            if not episode:
                logger.error("Episode not found", episode_id=str(episode_id))
                return
            
            if episode.status == EpisodeStatus.CANCELLED.value:
                logger.info("Episode cancelled", episode_id=str(episode_id))
                return
            
            # Mark as started
            episode.started_at = datetime.utcnow()
            await self.db.commit()
            
            # Get configuration
            config = EpisodeConfig(**episode.config) if episode.config else EpisodeConfig()
            
            # Get environment
            env = episode.environment
            if not env:
                await self._fail_episode(episode, "Environment not found")
                return
            
            # Run the episode pipeline
            await self._run_pipeline(episode, env, config)
            
        except Exception as e:
            logger.exception("Episode failed", episode_id=str(episode_id), error=str(e))
            try:
                result = await self.db.execute(
                    select(EpisodeDB).where(EpisodeDB.episode_id == episode_id)
                )
                episode = result.scalar_one_or_none()
                if episode:
                    await self._fail_episode(episode, str(e))
            except Exception:
                pass
    
    async def _run_pipeline(
        self,
        episode: EpisodeDB,
        env: EnvironmentDB,
        config: EpisodeConfig,
    ) -> None:
        """Run the full episode pipeline."""
        
        # Phase 1: Injection
        episode.status = EpisodeStatus.INJECTING.value
        await self.db.commit()
        
        logger.info("Phase 1: Injection", episode_id=str(episode.episode_id))
        
        async with Sandbox(image_ref=env.docker_image_ref) as sandbox:
            # Store container digest
            episode.container_image_digest = await sandbox.get_image_digest()
            
            # Initialize git for tracking
            await sandbox.git_init()
            await sandbox.git_tag("ssr-original")
            
            # Run injector agent
            injector = InjectorAgent(
                sandbox=sandbox,
                env_id=env.env_id,
                strategy=InjectionStrategy(config.injection_strategy),
                min_passing_tests=config.min_passing_tests,
                min_changed_files=config.min_changed_files,
                min_failing_tests=config.min_failing_tests,
                max_test_runtime_sec=config.max_test_runtime_sec,
            )
            
            artifact = await injector.run()
            
            if not artifact:
                await self._fail_episode(episode, "Injector failed to produce artifact")
                return
            
            # Store artifact
            artifact_db = await self._store_artifact(artifact)
            episode.artifact_id = artifact_db.artifact_id
            await self.db.commit()
            
            # Phase 2: Validation
            episode.status = EpisodeStatus.VALIDATING.value
            await self.db.commit()
            
            logger.info("Phase 2: Validation", episode_id=str(episode.episode_id))
            
            # Reset sandbox to original state
            await sandbox.bash("git checkout ssr-original -- .")
            
            validator = Validator(sandbox)
            validation_report = await validator.validate(artifact)
            
            # Store validation report
            report_db = await self._store_validation_report(validation_report)
            episode.validation_report_id = report_db.report_id
            await self.db.commit()
            
            if not validation_report.valid:
                # Artifact invalid - compute negative reward and complete
                episode.r_inject = -1.0
                episode.status = EpisodeStatus.COMPLETE.value
                episode.completed_at = datetime.utcnow()
                await self.db.commit()
                
                logger.info(
                    "Artifact invalid",
                    episode_id=str(episode.episode_id),
                    failed_steps=[s.name.value for s in validation_report.steps if not s.passed],
                )
                return
            
            # Phase 3: Solving
            episode.status = EpisodeStatus.SOLVING.value
            await self.db.commit()
            
            logger.info("Phase 3: Solving", episode_id=str(episode.episode_id))
            
            solver_attempts = []
            successful_attempts = 0
            
            for attempt_num in range(1, config.solver_attempts + 1):
                logger.info(
                    "Solver attempt",
                    episode_id=str(episode.episode_id),
                    attempt=attempt_num,
                    total=config.solver_attempts,
                )
                
                # Prepare buggy sandbox for solver
                await self._prepare_buggy_sandbox(sandbox, artifact)
                
                # Run solver agent
                solver = SolverAgent(
                    sandbox=sandbox,
                    artifact=artifact,
                    attempt_number=attempt_num,
                )
                
                attempt = await solver.run()
                
                # Phase 4: Evaluate this attempt
                if attempt.pred_patch:
                    evaluation = await self._evaluate_attempt(
                        sandbox, artifact, attempt
                    )
                    attempt.success = evaluation.success
                    attempt.test_summary = {
                        "passed": evaluation.tests_passed,
                        "failed": evaluation.tests_failed,
                    }
                    
                    if evaluation.success:
                        successful_attempts += 1
                
                # Store attempt
                attempt_db = await self._store_solver_attempt(episode.episode_id, attempt)
                solver_attempts.append(attempt)
                
                # Reset sandbox for next attempt
                await sandbox.bash("git checkout ssr-original -- .")
            
            # Phase 5: Compute metrics and rewards
            episode.status = EpisodeStatus.EVALUATING.value
            await self.db.commit()
            
            solve_rate = successful_attempts / config.solver_attempts
            episode.solve_rate = solve_rate
            
            # Compute injector reward (SSR paper Eq. (1))
            alpha = config.reward_alpha
            if solve_rate == 0 or solve_rate == 1:
                r_inject = -alpha
            else:
                r_inject = 1 - (1 + alpha) * solve_rate
            episode.r_inject = r_inject
            
            # Compute average solver reward (SSR paper Eq. (2))
            r_solve_values = [1.0 if a.success else -1.0 for a in solver_attempts]
            episode.r_solve_avg = sum(r_solve_values) / len(r_solve_values)
            
            # Mark complete
            episode.status = EpisodeStatus.COMPLETE.value
            episode.completed_at = datetime.utcnow()
            await self.db.commit()
            
            logger.info(
                "Episode complete",
                episode_id=str(episode.episode_id),
                solve_rate=solve_rate,
                r_inject=r_inject,
                r_solve_avg=episode.r_solve_avg,
            )
    
    async def _prepare_buggy_sandbox(
        self,
        sandbox: Sandbox,
        artifact: BugArtifact,
    ) -> None:
        """
        Prepare the sandbox in buggy state for solver.
        
        Applies bug_inject.diff and test_weaken.diff,
        then removes .git to prevent history leakage (SSR paper §2.4).
        """
        # Reset to original
        await sandbox.bash("git checkout ssr-original -- .")
        
        # Apply bug injection
        await sandbox.write_file("bug_inject.diff", artifact.bug_inject_diff)
        await sandbox.bash("patch -p1 < bug_inject.diff")
        
        # Apply test weakening
        await sandbox.write_file("test_weaken.diff", artifact.test_weaken_diff)
        await sandbox.bash("patch -p1 < test_weaken.diff")
        
        # Write test script and parser for solver
        await sandbox.write_file("test_script.sh", artifact.test_script)
        await sandbox.write_file("test_parser.py", artifact.test_parser)
        await sandbox.write_file("test_files.txt", "\n".join(artifact.test_files))
        await sandbox.bash("chmod +x test_script.sh")
        
        # Remove .git and reinitialize (leak prevention)
        await sandbox.git_init()
        await sandbox.git_tag("ssr-buggy")
    
    async def _evaluate_attempt(
        self,
        sandbox: Sandbox,
        artifact: BugArtifact,
        attempt: SolverAttempt,
    ) -> EvaluationReport:
        """
        Evaluate a solver attempt.
        
        Implements the evaluation pipeline from SSR paper §2.4, Fig. 7:
        1. Apply pred_patch
        2. Restore test files from original
        3. Run tests
        4. Check if all pass
        """
        logger.info("Evaluating attempt", attempt_id=str(attempt.attempt_id))
        
        start_time = datetime.utcnow()
        
        try:
            # Start from buggy state
            await sandbox.bash("git checkout ssr-buggy -- .")
            
            # Apply predicted patch
            if attempt.pred_patch:
                await sandbox.write_file("pred_patch.diff", attempt.pred_patch)
                result = await sandbox.bash("patch -p1 < pred_patch.diff")
                if result.exit_code != 0:
                    return EvaluationReport(
                        attempt_id=attempt.attempt_id,
                        success=False,
                        duration_ms=int((datetime.utcnow() - start_time).total_seconds() * 1000),
                    )
            
            # Restore test files from original (prevents "fixing by editing tests")
            for test_file in artifact.test_files:
                await sandbox.bash(f"git checkout ssr-original -- {test_file}")
            
            # Run tests
            test_result = await sandbox.bash(
                "bash test_script.sh 2>&1 | python test_parser.py",
                timeout=artifact.metadata.max_test_runtime_sec + 30,
            )
            
            # Parse results
            try:
                test_mapping = json.loads(test_result.stdout.strip())
                
                passed = sum(1 for s in test_mapping.values() if s == "passed")
                failed = sum(1 for s in test_mapping.values() if s != "passed")
                
                success = failed == 0
                
                return EvaluationReport(
                    attempt_id=attempt.attempt_id,
                    success=success,
                    tests_passed=passed,
                    tests_failed=failed,
                    tests_total=len(test_mapping),
                    per_test_status={
                        k: TestStatus(v) if v in ["passed", "failed"] else TestStatus.ERROR
                        for k, v in test_mapping.items()
                    },
                    test_files_restored=artifact.test_files,
                    duration_ms=int((datetime.utcnow() - start_time).total_seconds() * 1000),
                )
                
            except json.JSONDecodeError:
                return EvaluationReport(
                    attempt_id=attempt.attempt_id,
                    success=False,
                    duration_ms=int((datetime.utcnow() - start_time).total_seconds() * 1000),
                )
        
        except Exception as e:
            logger.error("Evaluation failed", error=str(e))
            return EvaluationReport(
                attempt_id=attempt.attempt_id,
                success=False,
                duration_ms=int((datetime.utcnow() - start_time).total_seconds() * 1000),
            )
    
    async def _store_artifact(self, artifact: BugArtifact) -> ArtifactDB:
        """Store artifact files and create database record."""
        # Store files
        refs = await self.storage.write_artifact_files(
            artifact_id=artifact.metadata.artifact_id,
            test_script=artifact.test_script,
            test_files=artifact.test_files,
            test_parser=artifact.test_parser,
            bug_inject_diff=artifact.bug_inject_diff,
            test_weaken_diff=artifact.test_weaken_diff,
        )
        
        # Create database record
        artifact_db = ArtifactDB(
            artifact_id=artifact.metadata.artifact_id,
            env_id=artifact.metadata.env_id,
            injection_strategy=artifact.metadata.injection_strategy.value,
            min_passing_tests=artifact.metadata.min_passing_tests,
            min_changed_files=artifact.metadata.min_changed_files,
            min_failing_tests=artifact.metadata.min_failing_tests,
            max_test_runtime_sec=artifact.metadata.max_test_runtime_sec,
            created_by_model=artifact.metadata.created_by_model,
            test_script_ref=refs["test_script_ref"],
            test_files_ref=refs["test_files_ref"],
            test_parser_ref=refs["test_parser_ref"],
            bug_inject_diff_ref=refs["bug_inject_diff_ref"],
            test_weaken_diff_ref=refs["test_weaken_diff_ref"],
            parent_artifact_id=artifact.parent_artifact_id,
            bug_order=artifact.bug_order,
        )
        
        self.db.add(artifact_db)
        await self.db.commit()
        await self.db.refresh(artifact_db)
        
        return artifact_db
    
    async def _store_validation_report(
        self, report: ValidationReport
    ) -> ValidationReportDB:
        """Store validation report."""
        report_db = ValidationReportDB(
            artifact_id=report.artifact_id,
            valid=report.valid,
            steps=[
                {
                    "name": step.name.value,
                    "passed": step.passed,
                    "details": step.details,
                    "error_message": step.error_message,
                    "duration_ms": step.duration_ms,
                }
                for step in report.steps
            ],
            total_duration_ms=report.total_duration_ms,
        )
        
        self.db.add(report_db)
        await self.db.commit()
        await self.db.refresh(report_db)
        
        return report_db
    
    async def _store_solver_attempt(
        self,
        episode_id: UUID,
        attempt: SolverAttempt,
    ) -> SolverAttemptDB:
        """Store solver attempt."""
        # Store predicted patch if present
        pred_patch_ref = None
        if attempt.pred_patch:
            pred_patch_ref = await self.storage.write(
                f"attempts/{attempt.attempt_id}/pred_patch.diff",
                attempt.pred_patch,
            )
        
        # Store tool trace
        tool_trace_ref = await self.storage.write(
            f"attempts/{attempt.attempt_id}/tool_trace.json",
            json.dumps([
                {
                    "timestamp": tc.timestamp.isoformat(),
                    "tool_name": tc.tool_name,
                    "arguments": tc.arguments,
                    "result": tc.result,
                    "duration_ms": tc.duration_ms,
                }
                for tc in attempt.tool_calls
            ]),
        )
        
        attempt_db = SolverAttemptDB(
            attempt_id=attempt.attempt_id,
            episode_id=episode_id,
            artifact_id=attempt.artifact_id,
            attempt_number=attempt.attempt_number,
            success=attempt.success,
            test_summary=attempt.test_summary,
            total_tool_steps=attempt.total_tool_steps,
            total_tokens_used=attempt.total_tokens_used,
            duration_ms=attempt.duration_ms,
            pred_patch_ref=pred_patch_ref,
            tool_trace_ref=tool_trace_ref,
        )
        
        self.db.add(attempt_db)
        await self.db.commit()
        await self.db.refresh(attempt_db)
        
        return attempt_db
    
    async def _fail_episode(self, episode: EpisodeDB, error_message: str) -> None:
        """Mark episode as failed."""
        episode.status = EpisodeStatus.FAILED.value
        episode.error_message = error_message
        episode.completed_at = datetime.utcnow()
        await self.db.commit()
        
        logger.error(
            "Episode failed",
            episode_id=str(episode.episode_id),
            error=error_message,
        )


class RewardCalculator:
    """
    Calculates SSR rewards.
    
    Implements:
    - Injector reward (Eq. 1): r_inject = 1 - (1+α)s or -α if s ∈ {0,1}
    - Solver reward (Eq. 2): r_solve = +1 if success else -1
    """
    
    def __init__(self, alpha: float = 0.8):
        self.alpha = alpha
    
    def compute_injector_reward(
        self,
        valid: bool,
        solve_rate: float,
    ) -> float:
        """
        Compute injector reward.
        
        Args:
            valid: Whether artifact passed validation
            solve_rate: s = successful_attempts / total_attempts
        
        Returns:
            Reward value
        """
        if not valid:
            return -1.0
        
        if solve_rate == 0.0 or solve_rate == 1.0:
            return -self.alpha
        
        return 1.0 - (1.0 + self.alpha) * solve_rate
    
    def compute_solver_reward(self, success: bool) -> float:
        """
        Compute solver reward.
        
        Args:
            success: Whether the attempt solved the bug
        
        Returns:
            +1.0 if success, -1.0 otherwise
        """
        return 1.0 if success else -1.0
