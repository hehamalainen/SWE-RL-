#!/usr/bin/env python3
"""
SSR Demo - Real Bug Injection and Repair Demo

This script demonstrates the core SSR duality:
1. An LLM injects a realistic bug into working code
2. The bug is validated (oracle test fails on buggy code, passes on clean)
3. A different LLM attempts to fix the bug using only the oracle test

Usage:
    python demo.py --api-key YOUR_OPENAI_KEY
    python demo.py --provider anthropic --api-key YOUR_ANTHROPIC_KEY
    
Requirements:
    pip install openai anthropic rich
"""

import argparse
import os
import sys
import json
import subprocess
import tempfile
import shutil
import difflib
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Tuple
from datetime import datetime

# Rich for nice terminal output
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.syntax import Syntax
    from rich.table import Table
    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.markdown import Markdown
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("Install 'rich' for better output: pip install rich")

console = Console() if RICH_AVAILABLE else None


@dataclass
class BugArtifact:
    """Represents an injected bug and its oracle test."""
    original_code: str
    buggy_code: str
    bug_diff: str
    oracle_test: str
    bug_description: str
    file_path: str
    test_file_path: str


@dataclass 
class SolveAttempt:
    """Represents a solver's attempt to fix the bug."""
    attempt_number: int
    proposed_fix: str
    fix_diff: str
    tests_passed: bool
    test_output: str
    reasoning: str


@dataclass
class EpisodeResult:
    """Complete result of an SSR episode."""
    artifact: Optional[BugArtifact] = None
    validation_passed: bool = False
    validation_details: dict = field(default_factory=dict)
    solve_attempts: List[SolveAttempt] = field(default_factory=list)
    solved: bool = False
    final_reward: float = 0.0
    duration_seconds: float = 0.0


class LLMClient:
    """Unified LLM client supporting OpenAI and Anthropic."""
    
    def __init__(self, provider: str, api_key: str, model: Optional[str] = None):
        self.provider = provider
        self.api_key = api_key
        
        if provider == "openai":
            self.model = model or "gpt-4-turbo"
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=api_key)
            except ImportError:
                raise ImportError("Install openai: pip install openai")
        elif provider == "anthropic":
            self.model = model or "claude-3-5-sonnet-20241022"
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=api_key)
            except ImportError:
                raise ImportError("Install anthropic: pip install anthropic")
        else:
            raise ValueError(f"Unknown provider: {provider}")
    
    def chat(self, system: str, user: str, temperature: float = 0.7) -> str:
        """Send a chat message and get response."""
        if self.provider == "openai":
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user}
                ],
                temperature=temperature,
                max_tokens=4096
            )
            return response.choices[0].message.content
        else:  # anthropic
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system,
                messages=[{"role": "user", "content": user}]
            )
            return response.content[0].text


INJECTOR_SYSTEM_PROMPT = """You are a bug injection expert. Your task is to inject a subtle, realistic bug into the provided code.

RULES:
1. The bug must be SUBTLE - something a developer might actually write by mistake
2. The bug must cause at least one test to fail
3. You must also write an ORACLE TEST that specifically catches this bug
4. The oracle test must PASS on the original code and FAIL on the buggy code

Bug categories to consider:
- Off-by-one errors in loops or indices
- Boundary condition errors
- Wrong comparison operators (< vs <=, == vs !=)
- Logic inversions (and vs or)
- Missing null/empty checks
- Type coercion issues
- Incorrect mathematical operations

OUTPUT FORMAT (JSON):
{
    "bug_description": "Brief description of the injected bug",
    "target_function": "Name of function being modified",
    "original_line": "The original line of code",
    "buggy_line": "The modified buggy line",
    "oracle_test": "def test_oracle_catches_bug():\n    # Test that catches the bug\n    ...",
    "reasoning": "Why this is a realistic bug"
}
"""

SOLVER_SYSTEM_PROMPT = """You are a skilled software engineer debugging a failing test.

You are given:
1. The source code (which has a bug somewhere)
2. A failing test that exposes the bug
3. The test output showing the failure

Your task is to:
1. Analyze the failing test to understand what it expects
2. Find the bug in the source code
3. Propose a fix

RULES:
- Only fix the actual bug, don't refactor or change unrelated code
- The fix should be minimal
- Explain your reasoning

OUTPUT FORMAT (JSON):
{
    "bug_location": "file:line or function name",
    "bug_analysis": "What the bug is and why the test fails",
    "original_line": "The buggy line",
    "fixed_line": "The corrected line",
    "reasoning": "Why this fix is correct"
}
"""


def print_header(text: str):
    """Print a section header."""
    if console:
        console.print(Panel(text, style="bold blue"))
    else:
        print(f"\n{'='*60}\n{text}\n{'='*60}")


def print_success(text: str):
    """Print success message."""
    if console:
        console.print(f"[green]✓[/green] {text}")
    else:
        print(f"✓ {text}")


def print_error(text: str):
    """Print error message."""
    if console:
        console.print(f"[red]✗[/red] {text}")
    else:
        print(f"✗ {text}")


def print_code(code: str, language: str = "python", title: str = ""):
    """Print code with syntax highlighting."""
    if console:
        syntax = Syntax(code, language, theme="monokai", line_numbers=True)
        if title:
            console.print(Panel(syntax, title=title))
        else:
            console.print(syntax)
    else:
        if title:
            print(f"\n--- {title} ---")
        print(code)


def print_diff(diff: str):
    """Print a diff with coloring."""
    if console:
        # Color the diff
        lines = diff.split('\n')
        for line in lines:
            if line.startswith('+') and not line.startswith('+++'):
                console.print(f"[green]{line}[/green]")
            elif line.startswith('-') and not line.startswith('---'):
                console.print(f"[red]{line}[/red]")
            elif line.startswith('@@'):
                console.print(f"[cyan]{line}[/cyan]")
            else:
                console.print(line)
    else:
        print(diff)


def run_tests(project_dir: Path, test_file: str = None) -> Tuple[bool, str]:
    """Run pytest in the project directory."""
    cmd = ["python", "-m", "pytest", "-v"]
    if test_file:
        cmd.append(test_file)
    
    result = subprocess.run(
        cmd,
        cwd=project_dir,
        capture_output=True,
        text=True,
        timeout=60
    )
    
    output = result.stdout + result.stderr
    passed = result.returncode == 0
    return passed, output


def create_diff(original: str, modified: str, filename: str = "file.py") -> str:
    """Create a unified diff between two strings."""
    original_lines = original.splitlines(keepends=True)
    modified_lines = modified.splitlines(keepends=True)
    
    diff = difflib.unified_diff(
        original_lines,
        modified_lines,
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}"
    )
    return ''.join(diff)


def inject_bug(client: LLMClient, source_code: str, filename: str) -> Optional[BugArtifact]:
    """Use LLM to inject a bug into the source code."""
    print_header("🐛 Phase 1: Bug Injection")
    
    if console:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Injector agent analyzing code...", total=None)
            
            user_prompt = f"""Here is the source code to inject a bug into:

```python
{source_code}
```

Filename: {filename}

Inject a subtle, realistic bug and provide an oracle test that catches it.
Remember: The oracle test must PASS on the original code and FAIL on the buggy code.
"""
            
            response = client.chat(INJECTOR_SYSTEM_PROMPT, user_prompt, temperature=0.8)
            progress.update(task, completed=True)
    else:
        print("Injector agent analyzing code...")
        user_prompt = f"""Here is the source code to inject a bug into:

```python
{source_code}
```

Filename: {filename}

Inject a subtle, realistic bug and provide an oracle test that catches it.
"""
        response = client.chat(INJECTOR_SYSTEM_PROMPT, user_prompt, temperature=0.8)
    
    # Parse JSON response
    try:
        # Extract JSON from response (handle markdown code blocks)
        if "```json" in response:
            json_str = response.split("```json")[1].split("```")[0]
        elif "```" in response:
            json_str = response.split("```")[1].split("```")[0]
        else:
            json_str = response
        
        data = json.loads(json_str.strip())
        
        # Create buggy code
        buggy_code = source_code.replace(
            data["original_line"].strip(),
            data["buggy_line"].strip()
        )
        
        if buggy_code == source_code:
            print_error("Failed to apply bug - line not found in source")
            if console:
                console.print(f"Looking for: {data['original_line']}")
            return None
        
        # Create oracle test file content
        oracle_test = f"""\"\"\"Oracle test for injected bug: {data['bug_description']}\"\"\"
import pytest
from calculator import Calculator, CalculatorError, DivisionByZeroError, InvalidInputError

{data['oracle_test']}
"""
        
        artifact = BugArtifact(
            original_code=source_code,
            buggy_code=buggy_code,
            bug_diff=create_diff(source_code, buggy_code, filename),
            oracle_test=oracle_test,
            bug_description=data["bug_description"],
            file_path=filename,
            test_file_path="test_oracle.py"
        )
        
        print_success(f"Bug injected: {data['bug_description']}")
        if console:
            console.print(f"\n[bold]Target function:[/bold] {data['target_function']}")
            console.print(f"[bold]Reasoning:[/bold] {data['reasoning']}")
        
        print_code(artifact.bug_diff, "diff", "Bug Diff")
        print_code(artifact.oracle_test, "python", "Oracle Test")
        
        return artifact
        
    except (json.JSONDecodeError, KeyError) as e:
        print_error(f"Failed to parse injector response: {e}")
        if console:
            console.print(f"[dim]Raw response: {response[:500]}...[/dim]")
        return None


def validate_bug(artifact: BugArtifact, project_dir: Path) -> Tuple[bool, dict]:
    """Validate that the injected bug is valid."""
    print_header("✓ Phase 2: Validation")
    
    validation = {
        "original_tests_pass": False,
        "oracle_passes_on_original": False,
        "oracle_fails_on_buggy": False,
        "details": {}
    }
    
    original_file = project_dir / artifact.file_path
    oracle_test_file = project_dir / artifact.test_file_path
    
    # Step 1: Original tests pass on original code
    print("Step 1: Checking original tests pass...")
    passed, output = run_tests(project_dir, "test_calculator.py")
    validation["original_tests_pass"] = passed
    validation["details"]["original_tests"] = output[-500:] if len(output) > 500 else output
    
    if passed:
        print_success("Original tests pass on original code")
    else:
        print_error("Original tests fail on original code (unexpected!)")
        return False, validation
    
    # Step 2: Oracle test passes on original code
    print("Step 2: Checking oracle passes on original code...")
    oracle_test_file.write_text(artifact.oracle_test)
    passed, output = run_tests(project_dir, artifact.test_file_path)
    validation["oracle_passes_on_original"] = passed
    validation["details"]["oracle_on_original"] = output[-500:] if len(output) > 500 else output
    
    if passed:
        print_success("Oracle test passes on original code")
    else:
        print_error("Oracle test fails on original code (bug in oracle test!)")
        oracle_test_file.unlink()
        return False, validation
    
    # Step 3: Apply bug and check oracle fails
    print("Step 3: Checking oracle fails on buggy code...")
    original_file.write_text(artifact.buggy_code)
    passed, output = run_tests(project_dir, artifact.test_file_path)
    validation["oracle_fails_on_buggy"] = not passed
    validation["details"]["oracle_on_buggy"] = output[-500:] if len(output) > 500 else output
    
    if not passed:
        print_success("Oracle test correctly fails on buggy code")
    else:
        print_error("Oracle test passes on buggy code (oracle doesn't catch the bug!)")
        # Restore original
        original_file.write_text(artifact.original_code)
        oracle_test_file.unlink()
        return False, validation
    
    # All validations passed - leave buggy code in place for solver
    overall = all([
        validation["original_tests_pass"],
        validation["oracle_passes_on_original"],
        validation["oracle_fails_on_buggy"]
    ])
    
    if overall:
        print_success("✓ All validation steps passed!")
    
    return overall, validation


def solve_bug(
    client: LLMClient,
    artifact: BugArtifact,
    project_dir: Path,
    max_attempts: int = 3
) -> List[SolveAttempt]:
    """Use LLM to attempt to fix the bug."""
    print_header("🔧 Phase 3: Bug Solving")
    
    attempts = []
    source_file = project_dir / artifact.file_path
    current_code = artifact.buggy_code
    
    for attempt_num in range(1, max_attempts + 1):
        if console:
            console.print(f"\n[bold]Attempt {attempt_num}/{max_attempts}[/bold]")
        else:
            print(f"\nAttempt {attempt_num}/{max_attempts}")
        
        # Get current test failure
        _, test_output = run_tests(project_dir, artifact.test_file_path)
        
        # Ask solver to fix
        user_prompt = f"""The following test is failing:

**Test File ({artifact.test_file_path}):**
```python
{artifact.oracle_test}
```

**Test Output:**
```
{test_output[-2000:]}
```

**Source Code ({artifact.file_path}):**
```python
{current_code}
```

Find and fix the bug that's causing the test to fail.
"""
        
        if console:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
            ) as progress:
                task = progress.add_task("Solver agent analyzing...", total=None)
                response = client.chat(SOLVER_SYSTEM_PROMPT, user_prompt, temperature=0.3)
                progress.update(task, completed=True)
        else:
            print("Solver agent analyzing...")
            response = client.chat(SOLVER_SYSTEM_PROMPT, user_prompt, temperature=0.3)
        
        # Parse response
        try:
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0]
            else:
                json_str = response
            
            data = json.loads(json_str.strip())
            
            # Apply fix
            fixed_code = current_code.replace(
                data["original_line"].strip(),
                data["fixed_line"].strip()
            )
            
            if fixed_code == current_code:
                print_error("Could not apply fix - line not found")
                attempt = SolveAttempt(
                    attempt_number=attempt_num,
                    proposed_fix=data.get("fixed_line", ""),
                    fix_diff="",
                    tests_passed=False,
                    test_output="Could not apply fix",
                    reasoning=data.get("reasoning", "")
                )
                attempts.append(attempt)
                continue
            
            # Write fixed code
            source_file.write_text(fixed_code)
            fix_diff = create_diff(current_code, fixed_code, artifact.file_path)
            
            if console:
                console.print(f"\n[bold]Proposed fix:[/bold]")
            print_diff(fix_diff)
            
            # Test the fix
            passed, output = run_tests(project_dir, artifact.test_file_path)
            
            attempt = SolveAttempt(
                attempt_number=attempt_num,
                proposed_fix=fixed_code,
                fix_diff=fix_diff,
                tests_passed=passed,
                test_output=output[-1000:],
                reasoning=data.get("reasoning", "")
            )
            attempts.append(attempt)
            
            if passed:
                print_success(f"Tests pass! Bug fixed on attempt {attempt_num}")
                
                # Verify original tests still pass
                all_passed, _ = run_tests(project_dir, "test_calculator.py")
                if all_passed:
                    print_success("Original tests still pass")
                else:
                    print_error("Fix broke original tests!")
                    attempt.tests_passed = False
                    # Revert
                    source_file.write_text(current_code)
                    continue
                
                return attempts
            else:
                print_error("Tests still failing")
                if console:
                    console.print(f"[dim]{output[-500:]}[/dim]")
                # Keep the buggy code for next attempt
                current_code = artifact.buggy_code
                source_file.write_text(current_code)
                
        except (json.JSONDecodeError, KeyError) as e:
            print_error(f"Failed to parse solver response: {e}")
            attempt = SolveAttempt(
                attempt_number=attempt_num,
                proposed_fix="",
                fix_diff="",
                tests_passed=False,
                test_output=f"Parse error: {e}",
                reasoning=""
            )
            attempts.append(attempt)
    
    return attempts


def run_episode(
    client: LLMClient,
    example_dir: Path,
    max_solve_attempts: int = 3
) -> EpisodeResult:
    """Run a complete SSR episode."""
    start_time = datetime.now()
    result = EpisodeResult()
    
    # Create working directory
    with tempfile.TemporaryDirectory() as tmpdir:
        work_dir = Path(tmpdir)
        
        # Copy example project
        shutil.copytree(example_dir, work_dir / "project")
        project_dir = work_dir / "project"
        
        # Read source code
        source_file = project_dir / "calculator.py"
        source_code = source_file.read_text()
        
        # Phase 1: Inject bug
        artifact = inject_bug(client, source_code, "calculator.py")
        if not artifact:
            result.duration_seconds = (datetime.now() - start_time).total_seconds()
            return result
        
        result.artifact = artifact
        
        # Phase 2: Validate
        valid, validation = validate_bug(artifact, project_dir)
        result.validation_passed = valid
        result.validation_details = validation
        
        if not valid:
            print_error("Validation failed - cannot proceed to solving")
            result.duration_seconds = (datetime.now() - start_time).total_seconds()
            return result
        
        # Phase 3: Solve
        attempts = solve_bug(client, artifact, project_dir, max_solve_attempts)
        result.solve_attempts = attempts
        result.solved = any(a.tests_passed for a in attempts)
        
        # Calculate reward
        if result.solved:
            result.final_reward = 1.0
        else:
            result.final_reward = 0.0
    
    result.duration_seconds = (datetime.now() - start_time).total_seconds()
    return result


def print_summary(result: EpisodeResult):
    """Print a summary of the episode."""
    print_header("📊 Episode Summary")
    
    if console:
        table = Table(title="Results")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Bug Injected", "✓" if result.artifact else "✗")
        table.add_row("Validation Passed", "✓" if result.validation_passed else "✗")
        table.add_row("Solve Attempts", str(len(result.solve_attempts)))
        table.add_row("Bug Solved", "✓" if result.solved else "✗")
        table.add_row("Final Reward", str(result.final_reward))
        table.add_row("Duration", f"{result.duration_seconds:.1f}s")
        
        console.print(table)
        
        if result.artifact:
            console.print(f"\n[bold]Bug Description:[/bold] {result.artifact.bug_description}")
    else:
        print(f"Bug Injected: {'Yes' if result.artifact else 'No'}")
        print(f"Validation Passed: {'Yes' if result.validation_passed else 'No'}")
        print(f"Solve Attempts: {len(result.solve_attempts)}")
        print(f"Bug Solved: {'Yes' if result.solved else 'No'}")
        print(f"Final Reward: {result.final_reward}")
        print(f"Duration: {result.duration_seconds:.1f}s")


def main():
    parser = argparse.ArgumentParser(
        description="SSR Demo - Bug Injection and Repair",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python demo.py --api-key sk-...
    python demo.py --provider anthropic --api-key sk-ant-...
    python demo.py --provider openai --model gpt-4o --api-key sk-...
        """
    )
    parser.add_argument(
        "--provider",
        choices=["openai", "anthropic"],
        default="openai",
        help="LLM provider (default: openai)"
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY"),
        help="API key (or set OPENAI_API_KEY/ANTHROPIC_API_KEY env var)"
    )
    parser.add_argument(
        "--model",
        help="Model to use (default: gpt-4-turbo for OpenAI, claude-3-5-sonnet for Anthropic)"
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="Maximum solve attempts (default: 3)"
    )
    parser.add_argument(
        "--example-dir",
        type=Path,
        default=Path(__file__).parent / "examples" / "calculator",
        help="Path to example project"
    )
    
    args = parser.parse_args()
    
    if not args.api_key:
        print_error("No API key provided. Use --api-key or set OPENAI_API_KEY/ANTHROPIC_API_KEY")
        sys.exit(1)
    
    if not args.example_dir.exists():
        print_error(f"Example directory not found: {args.example_dir}")
        sys.exit(1)
    
    print_header("🚀 SSR Demo - Self-Play Bug Injection & Repair")
    
    if console:
        console.print(f"Provider: [cyan]{args.provider}[/cyan]")
        console.print(f"Model: [cyan]{args.model or 'default'}[/cyan]")
        console.print(f"Example: [cyan]{args.example_dir}[/cyan]")
        console.print()
    
    # Initialize client
    client = LLMClient(args.provider, args.api_key, args.model)
    
    # Run episode
    result = run_episode(client, args.example_dir, args.max_attempts)
    
    # Print summary
    print_summary(result)
    
    # Return appropriate exit code
    sys.exit(0 if result.solved else 1)


if __name__ == "__main__":
    main()
