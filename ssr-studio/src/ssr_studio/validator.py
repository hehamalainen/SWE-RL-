"""
Consistency Validation Engine for SSR Studio.

Implements the SSR paper's validation checks (§2.3, Fig. 4):
1. Test file existence and coverage
2. Test parser validity
3. Test script validity on original codebase
4. Bug scope validation
5. Bug validity (tests fail after bug injection)
6. Test weakening validity
7. Inverse mutation testing

Each modified file in bug_inject.diff must contribute to test failures.
"""

import json
import re
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import structlog

from ssr_studio.config import settings, validator_config
from ssr_studio.models import (
    BugArtifact,
    ValidationReport,
    ValidationStepResult,
    ValidationStepName,
    TestStatus,
)
from ssr_studio.sandbox import Sandbox

logger = structlog.get_logger()


@dataclass
class ValidationContext:
    """Context for validation operations."""
    artifact: BugArtifact
    sandbox: Sandbox
    test_mapping: dict[str, TestStatus] | None = None
    bug_test_mapping: dict[str, TestStatus] | None = None
    weak_test_mapping: dict[str, TestStatus] | None = None
    changed_code_files: list[str] | None = None
    changed_test_files: list[str] | None = None


class Validator:
    """
    Validates bug artifacts according to SSR paper requirements.
    
    The validator ensures artifacts meet all consistency checks before
    they can be used for solver training.
    """
    
    def __init__(self, sandbox: Sandbox):
        self.sandbox = sandbox
        self._logs: list[str] = []
    
    def _log(self, message: str, **kwargs) -> None:
        """Log a validation message."""
        log_entry = f"[{time.strftime('%H:%M:%S')}] {message}"
        if kwargs:
            log_entry += f" | {kwargs}"
        self._logs.append(log_entry)
        logger.info(message, **kwargs)
    
    async def validate(self, artifact: BugArtifact) -> ValidationReport:
        """
        Run all validation steps on an artifact.
        
        Returns a ValidationReport with pass/fail status for each step.
        """
        self._logs = []
        start_time = time.time()
        
        ctx = ValidationContext(artifact=artifact, sandbox=self.sandbox)
        steps: list[ValidationStepResult] = []
        
        # Step 1: Test files existence
        step1 = await self._validate_test_files_existence(ctx)
        steps.append(step1)
        if not step1.passed:
            return self._build_report(artifact.metadata.artifact_id, steps, start_time)
        
        # Step 2: Parser validity
        step2 = await self._validate_parser(ctx)
        steps.append(step2)
        if not step2.passed:
            return self._build_report(artifact.metadata.artifact_id, steps, start_time)
        
        # Step 3: Original tests pass
        step3 = await self._validate_original_tests(ctx)
        steps.append(step3)
        if not step3.passed:
            return self._build_report(artifact.metadata.artifact_id, steps, start_time)
        
        # Step 4: Bug scope
        step4 = await self._validate_bug_scope(ctx)
        steps.append(step4)
        if not step4.passed:
            return self._build_report(artifact.metadata.artifact_id, steps, start_time)
        
        # Step 5: Bug validity (tests fail after bug)
        step5 = await self._validate_bug_validity(ctx)
        steps.append(step5)
        if not step5.passed:
            return self._build_report(artifact.metadata.artifact_id, steps, start_time)
        
        # Step 6: Test weakening validity
        step6 = await self._validate_test_weakening(ctx)
        steps.append(step6)
        if not step6.passed:
            return self._build_report(artifact.metadata.artifact_id, steps, start_time)
        
        # Step 7: Inverse mutation testing (if enabled)
        if validator_config.enable_inverse_mutation:
            step7 = await self._validate_inverse_mutation(ctx)
            steps.append(step7)
        
        return self._build_report(artifact.metadata.artifact_id, steps, start_time)
    
    async def _validate_test_files_existence(
        self, ctx: ValidationContext
    ) -> ValidationStepResult:
        """
        Step 1: Validate that all test files exist.
        
        - All files in test_files.txt must exist in the original repo
        - test_weaken.diff should only touch files in test_files.txt
        """
        step_start = time.time()
        self._log("Validating test files existence")
        
        try:
            test_files = ctx.artifact.test_files
            missing_files = []
            
            for test_file in test_files:
                result = await self.sandbox.bash(f"test -f {test_file}")
                if result.exit_code != 0:
                    missing_files.append(test_file)
            
            if missing_files:
                return ValidationStepResult(
                    name=ValidationStepName.TEST_FILES_EXISTENCE,
                    passed=False,
                    details={"missing_files": missing_files},
                    error_message=f"Missing test files: {missing_files}",
                    duration_ms=int((time.time() - step_start) * 1000),
                )
            
            # Parse test_weaken.diff to get changed files
            weak_diff_files = self._parse_diff_files(ctx.artifact.test_weaken_diff)
            ctx.changed_test_files = weak_diff_files
            
            # Check that weakening diff only touches test files
            non_test_files = [f for f in weak_diff_files if f not in test_files]
            if non_test_files:
                return ValidationStepResult(
                    name=ValidationStepName.TEST_FILES_EXISTENCE,
                    passed=False,
                    details={
                        "test_files": test_files,
                        "weak_diff_files": weak_diff_files,
                        "non_test_files": non_test_files,
                    },
                    error_message=f"test_weaken.diff modifies non-test files: {non_test_files}",
                    duration_ms=int((time.time() - step_start) * 1000),
                )
            
            return ValidationStepResult(
                name=ValidationStepName.TEST_FILES_EXISTENCE,
                passed=True,
                details={"test_files_count": len(test_files)},
                duration_ms=int((time.time() - step_start) * 1000),
            )
        
        except Exception as e:
            return ValidationStepResult(
                name=ValidationStepName.TEST_FILES_EXISTENCE,
                passed=False,
                error_message=str(e),
                duration_ms=int((time.time() - step_start) * 1000),
            )
    
    async def _validate_parser(self, ctx: ValidationContext) -> ValidationStepResult:
        """
        Step 2: Validate test parser produces valid JSON mapping.
        
        Run: bash test_script.sh | python test_parser.py
        Output should be valid JSON: {test_id: "passed"|"failed"|...}
        """
        step_start = time.time()
        self._log("Validating test parser")
        
        try:
            # Write test script and parser to sandbox
            await self.sandbox.write_file("test_script.sh", ctx.artifact.test_script)
            await self.sandbox.write_file("test_parser.py", ctx.artifact.test_parser)
            await self.sandbox.bash("chmod +x test_script.sh")
            
            # Run test script and pipe to parser
            result = await self.sandbox.bash(
                "bash test_script.sh 2>&1 | python test_parser.py",
                timeout=ctx.artifact.metadata.max_test_runtime_sec,
            )
            
            if result.timeout:
                return ValidationStepResult(
                    name=ValidationStepName.PARSER_VALIDITY,
                    passed=False,
                    error_message=f"Test script timed out after {ctx.artifact.metadata.max_test_runtime_sec}s",
                    duration_ms=int((time.time() - step_start) * 1000),
                )
            
            if result.exit_code != 0:
                return ValidationStepResult(
                    name=ValidationStepName.PARSER_VALIDITY,
                    passed=False,
                    details={"stderr": result.stderr[:1000]},
                    error_message=f"Parser failed with exit code {result.exit_code}",
                    duration_ms=int((time.time() - step_start) * 1000),
                )
            
            # Parse JSON output
            try:
                test_mapping = json.loads(result.stdout.strip())
                if not isinstance(test_mapping, dict):
                    raise ValueError("Parser output must be a JSON object")
                
                ctx.test_mapping = {
                    k: TestStatus(v) if v in TestStatus.__members__.values() else TestStatus.PASSED
                    for k, v in test_mapping.items()
                }
                
            except json.JSONDecodeError as e:
                return ValidationStepResult(
                    name=ValidationStepName.PARSER_VALIDITY,
                    passed=False,
                    details={"output_preview": result.stdout[:500]},
                    error_message=f"Invalid JSON from parser: {e}",
                    duration_ms=int((time.time() - step_start) * 1000),
                )
            
            return ValidationStepResult(
                name=ValidationStepName.PARSER_VALIDITY,
                passed=True,
                details={"test_count": len(ctx.test_mapping)},
                duration_ms=int((time.time() - step_start) * 1000),
            )
        
        except Exception as e:
            return ValidationStepResult(
                name=ValidationStepName.PARSER_VALIDITY,
                passed=False,
                error_message=str(e),
                duration_ms=int((time.time() - step_start) * 1000),
            )
    
    async def _validate_original_tests(
        self, ctx: ValidationContext
    ) -> ValidationStepResult:
        """
        Step 3: Validate all tests pass on original codebase.
        
        - All tests should pass
        - Number of passing tests >= min_passing_tests
        """
        step_start = time.time()
        self._log("Validating original tests pass")
        
        try:
            if not ctx.test_mapping:
                return ValidationStepResult(
                    name=ValidationStepName.ORIGINAL_TESTS_PASS,
                    passed=False,
                    error_message="No test mapping available",
                    duration_ms=int((time.time() - step_start) * 1000),
                )
            
            # Check all tests pass
            failed_tests = [
                test_id for test_id, status in ctx.test_mapping.items()
                if status != TestStatus.PASSED
            ]
            
            if failed_tests:
                return ValidationStepResult(
                    name=ValidationStepName.ORIGINAL_TESTS_PASS,
                    passed=False,
                    details={
                        "failed_tests": failed_tests[:10],
                        "failed_count": len(failed_tests),
                    },
                    error_message=f"{len(failed_tests)} tests failed on original codebase",
                    duration_ms=int((time.time() - step_start) * 1000),
                )
            
            # Check minimum passing tests
            passing_count = len(ctx.test_mapping)
            min_required = ctx.artifact.metadata.min_passing_tests
            
            if passing_count < min_required:
                return ValidationStepResult(
                    name=ValidationStepName.ORIGINAL_TESTS_PASS,
                    passed=False,
                    details={"passing_count": passing_count, "min_required": min_required},
                    error_message=f"Only {passing_count} tests, need at least {min_required}",
                    duration_ms=int((time.time() - step_start) * 1000),
                )
            
            return ValidationStepResult(
                name=ValidationStepName.ORIGINAL_TESTS_PASS,
                passed=True,
                details={"num_tests": passing_count},
                duration_ms=int((time.time() - step_start) * 1000),
            )
        
        except Exception as e:
            return ValidationStepResult(
                name=ValidationStepName.ORIGINAL_TESTS_PASS,
                passed=False,
                error_message=str(e),
                duration_ms=int((time.time() - step_start) * 1000),
            )
    
    async def _validate_bug_scope(self, ctx: ValidationContext) -> ValidationStepResult:
        """
        Step 4: Validate bug scope.
        
        - bug_inject.diff modifies >= min_changed_files code files
        - bug_inject.diff should NOT modify test files
        """
        step_start = time.time()
        self._log("Validating bug scope")
        
        try:
            # Parse bug_inject.diff to get changed files
            changed_files = self._parse_diff_files(ctx.artifact.bug_inject_diff)
            ctx.changed_code_files = changed_files
            
            # Check that bug diff doesn't touch test files
            test_files_modified = [
                f for f in changed_files if f in ctx.artifact.test_files
            ]
            
            if test_files_modified:
                return ValidationStepResult(
                    name=ValidationStepName.BUG_SCOPE,
                    passed=False,
                    details={"test_files_modified": test_files_modified},
                    error_message=f"bug_inject.diff modifies test files: {test_files_modified}",
                    duration_ms=int((time.time() - step_start) * 1000),
                )
            
            # Check minimum changed files
            min_required = ctx.artifact.metadata.min_changed_files
            
            if len(changed_files) < min_required:
                return ValidationStepResult(
                    name=ValidationStepName.BUG_SCOPE,
                    passed=False,
                    details={
                        "changed_files": len(changed_files),
                        "min_required": min_required,
                    },
                    error_message=f"Only {len(changed_files)} files changed, need at least {min_required}",
                    duration_ms=int((time.time() - step_start) * 1000),
                )
            
            return ValidationStepResult(
                name=ValidationStepName.BUG_SCOPE,
                passed=True,
                details={"changed_files": len(changed_files), "files": changed_files},
                duration_ms=int((time.time() - step_start) * 1000),
            )
        
        except Exception as e:
            return ValidationStepResult(
                name=ValidationStepName.BUG_SCOPE,
                passed=False,
                error_message=str(e),
                duration_ms=int((time.time() - step_start) * 1000),
            )
    
    async def _validate_bug_validity(
        self, ctx: ValidationContext
    ) -> ValidationStepResult:
        """
        Step 5: Validate bug causes test failures.
        
        After applying bug_inject.diff:
        - At least min_failing_tests tests should fail
        """
        step_start = time.time()
        self._log("Validating bug validity")
        
        try:
            # Apply bug injection patch
            await self.sandbox.write_file("bug_inject.diff", ctx.artifact.bug_inject_diff)
            result = await self.sandbox.bash("patch -p1 < bug_inject.diff")
            
            if result.exit_code != 0:
                return ValidationStepResult(
                    name=ValidationStepName.BUG_VALIDITY,
                    passed=False,
                    details={"stderr": result.stderr[:1000]},
                    error_message="Failed to apply bug_inject.diff",
                    duration_ms=int((time.time() - step_start) * 1000),
                )
            
            # Run tests again
            test_result = await self.sandbox.bash(
                "bash test_script.sh 2>&1 | python test_parser.py",
                timeout=ctx.artifact.metadata.max_test_runtime_sec,
            )
            
            if test_result.timeout:
                return ValidationStepResult(
                    name=ValidationStepName.BUG_VALIDITY,
                    passed=False,
                    error_message="Test script timed out after bug injection",
                    duration_ms=int((time.time() - step_start) * 1000),
                )
            
            # Parse test results
            try:
                bug_mapping = json.loads(test_result.stdout.strip())
                ctx.bug_test_mapping = {
                    k: TestStatus(v) if v in TestStatus.__members__.values() else TestStatus.FAILED
                    for k, v in bug_mapping.items()
                }
            except json.JSONDecodeError:
                return ValidationStepResult(
                    name=ValidationStepName.BUG_VALIDITY,
                    passed=False,
                    error_message="Failed to parse test results after bug injection",
                    duration_ms=int((time.time() - step_start) * 1000),
                )
            
            # Count failing tests
            failing_tests = [
                test_id for test_id, status in ctx.bug_test_mapping.items()
                if status == TestStatus.FAILED
            ]
            
            min_required = ctx.artifact.metadata.min_failing_tests
            
            if len(failing_tests) < min_required:
                return ValidationStepResult(
                    name=ValidationStepName.BUG_VALIDITY,
                    passed=False,
                    details={
                        "failing_tests": len(failing_tests),
                        "min_required": min_required,
                    },
                    error_message=f"Only {len(failing_tests)} tests fail, need at least {min_required}",
                    duration_ms=int((time.time() - step_start) * 1000),
                )
            
            return ValidationStepResult(
                name=ValidationStepName.BUG_VALIDITY,
                passed=True,
                details={"failing_tests": len(failing_tests)},
                duration_ms=int((time.time() - step_start) * 1000),
            )
        
        except Exception as e:
            return ValidationStepResult(
                name=ValidationStepName.BUG_VALIDITY,
                passed=False,
                error_message=str(e),
                duration_ms=int((time.time() - step_start) * 1000),
            )
    
    async def _validate_test_weakening(
        self, ctx: ValidationContext
    ) -> ValidationStepResult:
        """
        Step 6: Validate test weakening.
        
        After applying test_weaken.diff:
        - Some tests that failed in buggy state should now pass
        """
        step_start = time.time()
        self._log("Validating test weakening")
        
        try:
            # Apply test weakening patch
            await self.sandbox.write_file("test_weaken.diff", ctx.artifact.test_weaken_diff)
            result = await self.sandbox.bash("patch -p1 < test_weaken.diff")
            
            if result.exit_code != 0:
                return ValidationStepResult(
                    name=ValidationStepName.TEST_WEAKENING_VALIDITY,
                    passed=False,
                    details={"stderr": result.stderr[:1000]},
                    error_message="Failed to apply test_weaken.diff",
                    duration_ms=int((time.time() - step_start) * 1000),
                )
            
            # Run tests again
            test_result = await self.sandbox.bash(
                "bash test_script.sh 2>&1 | python test_parser.py",
                timeout=ctx.artifact.metadata.max_test_runtime_sec,
            )
            
            # Parse test results
            try:
                weak_mapping = json.loads(test_result.stdout.strip())
                ctx.weak_test_mapping = {
                    k: TestStatus(v) if v in TestStatus.__members__.values() else TestStatus.FAILED
                    for k, v in weak_mapping.items()
                }
            except json.JSONDecodeError:
                return ValidationStepResult(
                    name=ValidationStepName.TEST_WEAKENING_VALIDITY,
                    passed=False,
                    error_message="Failed to parse test results after weakening",
                    duration_ms=int((time.time() - step_start) * 1000),
                )
            
            # Check that some previously failing tests now pass
            recovered_tests = []
            if ctx.bug_test_mapping:
                for test_id, status in ctx.weak_test_mapping.items():
                    bug_status = ctx.bug_test_mapping.get(test_id)
                    if bug_status == TestStatus.FAILED and status == TestStatus.PASSED:
                        recovered_tests.append(test_id)
            
            if not recovered_tests:
                return ValidationStepResult(
                    name=ValidationStepName.TEST_WEAKENING_VALIDITY,
                    passed=False,
                    error_message="No tests recovered after applying test_weaken.diff",
                    duration_ms=int((time.time() - step_start) * 1000),
                )
            
            return ValidationStepResult(
                name=ValidationStepName.TEST_WEAKENING_VALIDITY,
                passed=True,
                details={"recovered_tests": len(recovered_tests)},
                duration_ms=int((time.time() - step_start) * 1000),
            )
        
        except Exception as e:
            return ValidationStepResult(
                name=ValidationStepName.TEST_WEAKENING_VALIDITY,
                passed=False,
                error_message=str(e),
                duration_ms=int((time.time() - step_start) * 1000),
            )
    
    async def _validate_inverse_mutation(
        self, ctx: ValidationContext
    ) -> ValidationStepResult:
        """
        Step 7: Inverse mutation testing.
        
        For each modified file in bug_inject.diff:
        - Revert that file (keeping others buggy)
        - At least one failing oracle test should now pass
        
        This ensures each modified file contributes to the bug.
        """
        step_start = time.time()
        self._log("Validating inverse mutation testing")
        
        try:
            if not ctx.changed_code_files:
                return ValidationStepResult(
                    name=ValidationStepName.INVERSE_MUTATION_TESTING,
                    passed=False,
                    error_message="No changed code files to test",
                    duration_ms=int((time.time() - step_start) * 1000),
                )
            
            if not ctx.bug_test_mapping:
                return ValidationStepResult(
                    name=ValidationStepName.INVERSE_MUTATION_TESTING,
                    passed=False,
                    error_message="No bug test mapping available",
                    duration_ms=int((time.time() - step_start) * 1000),
                )
            
            # Get failing tests from oracle (bug state, not weakened)
            failing_tests = [
                test_id for test_id, status in ctx.bug_test_mapping.items()
                if status == TestStatus.FAILED
            ]
            
            # First, reset to original state and re-apply bug
            await self.sandbox.bash("patch -R -p1 < test_weaken.diff")
            await self.sandbox.bash("patch -R -p1 < bug_inject.diff")
            
            # For each modified file, test if reverting it helps
            non_contributing_files = []
            
            for file_path in ctx.changed_code_files:
                # Re-apply full bug
                await self.sandbox.bash("patch -p1 < bug_inject.diff")
                
                # Revert just this file to original
                await self.sandbox.bash(f"git checkout HEAD -- {file_path}")
                
                # Run oracle tests (without weakening)
                test_result = await self.sandbox.bash(
                    "bash test_script.sh 2>&1 | python test_parser.py",
                    timeout=ctx.artifact.metadata.max_test_runtime_sec,
                )
                
                try:
                    partial_mapping = json.loads(test_result.stdout.strip())
                except json.JSONDecodeError:
                    continue
                
                # Check if any previously failing test now passes
                recovered = False
                for test_id in failing_tests:
                    old_status = ctx.bug_test_mapping.get(test_id)
                    new_status = partial_mapping.get(test_id)
                    if old_status == TestStatus.FAILED and new_status == "passed":
                        recovered = True
                        break
                
                if not recovered:
                    non_contributing_files.append(file_path)
                
                # Reset for next iteration
                await self.sandbox.bash("patch -R -p1 < bug_inject.diff")
            
            if non_contributing_files:
                return ValidationStepResult(
                    name=ValidationStepName.INVERSE_MUTATION_TESTING,
                    passed=False,
                    details={"non_contributing_files": non_contributing_files},
                    error_message=f"Files don't contribute to bug: {non_contributing_files}",
                    duration_ms=int((time.time() - step_start) * 1000),
                )
            
            return ValidationStepResult(
                name=ValidationStepName.INVERSE_MUTATION_TESTING,
                passed=True,
                details={"tested_files": len(ctx.changed_code_files)},
                duration_ms=int((time.time() - step_start) * 1000),
            )
        
        except Exception as e:
            return ValidationStepResult(
                name=ValidationStepName.INVERSE_MUTATION_TESTING,
                passed=False,
                error_message=str(e),
                duration_ms=int((time.time() - step_start) * 1000),
            )
    
    def _parse_diff_files(self, diff_content: str) -> list[str]:
        """
        Parse a unified diff to extract list of modified files.
        
        Looks for lines like:
        --- a/path/to/file.py
        +++ b/path/to/file.py
        """
        files = set()
        
        # Match --- a/... or +++ b/... patterns
        pattern = r'^(?:---|\+\+\+) [ab]/(.+)$'
        
        for line in diff_content.split('\n'):
            match = re.match(pattern, line)
            if match:
                file_path = match.group(1)
                # Skip /dev/null (for added/deleted files)
                if file_path != '/dev/null':
                    files.add(file_path)
        
        return list(files)
    
    def _build_report(
        self,
        artifact_id: UUID,
        steps: list[ValidationStepResult],
        start_time: float,
    ) -> ValidationReport:
        """Build the final validation report."""
        total_duration_ms = int((time.time() - start_time) * 1000)
        all_passed = all(step.passed for step in steps)
        
        return ValidationReport(
            artifact_id=artifact_id,
            valid=all_passed,
            steps=steps,
            total_duration_ms=total_duration_ms,
        )
    
    def get_logs(self) -> str:
        """Get all validation logs."""
        return "\n".join(self._logs)
