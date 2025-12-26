"""
Bug Solver Agent for SSR Studio.

Implements the solver role from the SSR paper (§2.4, Appendix A.2):
- Receives a buggy codebase with oracle test specification
- Explores and understands the bug
- Creates a fix patch
- Submits the patch for evaluation
"""

import json
from datetime import datetime
from typing import Any
from uuid import UUID

import structlog

from ssr_studio.config import settings
from ssr_studio.models import (
    BugArtifact,
    SolverAttempt,
    ToolCall as ToolCallRecord,
    TestStatus,
)
from ssr_studio.model_gateway import (
    ModelGateway,
    Message,
    Role,
    ToolCall,
    get_model_gateway,
)
from ssr_studio.sandbox import Sandbox
from ssr_studio.tools import SOLVER_TOOLS

logger = structlog.get_logger()


# =============================================================================
# System Prompts (SSR paper Appendix A.2)
# =============================================================================

SOLVER_SYSTEM_PROMPT = """You are an expert software engineer tasked with fixing a bug in a codebase.

The codebase has a bug that causes some tests to fail. Your goal is to:
1. Understand the failing tests from the oracle specification below
2. Explore the codebase to find the bug
3. Fix the bug by modifying the code (NOT the tests)
4. Verify your fix by running tests
5. Submit your fix as a patch

ORACLE TEST SPECIFICATION:
The following diff shows test assertions that should pass but currently fail.
Your fix should make these tests pass:

```diff
{oracle_test_patch}
```

IMPORTANT RULES:
- Do NOT modify test files - only fix the source code
- Do NOT look at git history (it has been removed for this task)
- The bug is in the source code, not in the tests
- Run tests frequently to verify your progress
- Submit your fix using the submit_patch tool when all tests pass

AVAILABLE TOOLS:
- bash: Run shell commands
- read_file: Read file contents
- edit_file: Edit files
- list_dir: List directory contents
- find_files: Find files by pattern
- run_tests: Run the test suite
- create_diff: Create a diff of your changes
- submit_patch: Submit your fix

When ready, use create_diff to see your changes, then submit_patch to submit.
"""


class SolverAgent:
    """
    Bug solving agent that fixes bugs specified by oracle tests.
    
    The agent receives:
    - A buggy codebase (with bug_inject.diff and test_weaken.diff applied)
    - Oracle test specification (reversed test_weaken.diff)
    
    And produces:
    - pred_patch.diff (predicted fix)
    """
    
    def __init__(
        self,
        sandbox: Sandbox,
        artifact: BugArtifact,
        attempt_number: int = 1,
        model_gateway: ModelGateway | None = None,
        max_tool_steps: int | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ):
        self.sandbox = sandbox
        self.artifact = artifact
        self.attempt_number = attempt_number
        self.gateway = model_gateway or get_model_gateway()
        
        # Configuration
        self.max_tool_steps = max_tool_steps or settings.solver_max_tool_steps
        self.max_tokens = max_tokens or settings.solver_max_tokens
        self.temperature = temperature or settings.solver_temperature
        
        # State
        self._messages: list[Message] = []
        self._tool_calls: list[ToolCallRecord] = []
        self._pred_patch: str | None = None
        self._submitted = False
        self._total_tokens = 0
    
    def _get_oracle_test_patch(self) -> str:
        """
        Get the oracle test specification.
        
        This is the REVERSED test_weaken.diff - it shows what tests
        should pass but are currently "weakened" (disabled/modified).
        """
        # Reverse the test weakening patch
        # In a real implementation, we'd use patch -R or parse the diff
        return self._reverse_diff(self.artifact.test_weaken_diff)
    
    def _reverse_diff(self, diff: str) -> str:
        """
        Reverse a unified diff.
        
        Swaps + and - lines, and swaps a/ and b/ prefixes.
        """
        lines = []
        for line in diff.split('\n'):
            if line.startswith('---'):
                lines.append(line.replace('--- a/', '--- b/').replace('--- b/', '--- a/'))
            elif line.startswith('+++'):
                lines.append(line.replace('+++ b/', '+++ a/').replace('+++ a/', '+++ b/'))
            elif line.startswith('+') and not line.startswith('+++'):
                lines.append('-' + line[1:])
            elif line.startswith('-') and not line.startswith('---'):
                lines.append('+' + line[1:])
            else:
                lines.append(line)
        return '\n'.join(lines)
    
    def _get_system_prompt(self) -> str:
        """Generate the system prompt with oracle specification."""
        oracle_patch = self._get_oracle_test_patch()
        return SOLVER_SYSTEM_PROMPT.format(oracle_test_patch=oracle_patch)
    
    async def run(self) -> SolverAttempt:
        """
        Run the solver agent to produce a fix patch.
        
        Returns:
            SolverAttempt with the prediction and evaluation
        """
        logger.info(
            "Starting solver agent",
            artifact_id=str(self.artifact.metadata.artifact_id),
            attempt=self.attempt_number,
            max_steps=self.max_tool_steps,
        )
        
        start_time = datetime.utcnow()
        
        # Initialize conversation
        self._messages = [
            Message(role=Role.SYSTEM, content=self._get_system_prompt()),
            Message(
                role=Role.USER,
                content="Please fix the bug in this codebase. "
                        "Start by exploring the codebase and understanding the failing tests.",
            ),
        ]
        
        for step in range(self.max_tool_steps):
            if self._submitted:
                break
            
            # Check token budget
            if self._total_tokens >= self.max_tokens:
                logger.warning("Token budget exceeded", tokens=self._total_tokens)
                break
            
            logger.info("Solver step", step=step + 1, max_steps=self.max_tool_steps)
            
            # Generate next action
            result = await self.gateway.generate(
                role="solver",
                messages=self._messages,
                tools=SOLVER_TOOLS,
                temperature=self.temperature,
            )
            
            self._total_tokens += result.total_tokens
            
            # Handle response
            if result.tool_calls:
                for tool_call in result.tool_calls:
                    tool_result = await self._execute_tool(tool_call)
                    
                    # Add assistant message with tool call
                    self._messages.append(Message(
                        role=Role.ASSISTANT,
                        content=result.content or "",
                        tool_calls=[{
                            "id": tool_call.id,
                            "type": "function",
                            "function": {
                                "name": tool_call.name,
                                "arguments": json.dumps(tool_call.arguments),
                            },
                        }],
                    ))
                    
                    # Add tool result
                    self._messages.append(Message(
                        role=Role.TOOL,
                        content=tool_result,
                        tool_call_id=tool_call.id,
                    ))
                    
                    if self._submitted:
                        break
            else:
                if result.content:
                    self._messages.append(Message(
                        role=Role.ASSISTANT,
                        content=result.content,
                    ))
                    
                    self._messages.append(Message(
                        role=Role.USER,
                        content="Please continue. Use tools to explore the code, "
                                "make fixes, and run tests.",
                    ))
        
        # Build attempt record
        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        return SolverAttempt(
            artifact_id=self.artifact.metadata.artifact_id,
            attempt_number=self.attempt_number,
            oracle_test_patch=self._get_oracle_test_patch(),
            pred_patch=self._pred_patch,
            success=False,  # Will be set by evaluator
            total_tool_steps=len(self._tool_calls),
            total_tokens_used=self._total_tokens,
            duration_ms=duration_ms,
            tool_calls=self._tool_calls,
        )
    
    async def _execute_tool(self, tool_call: ToolCall) -> str:
        """Execute a tool call and return the result."""
        start_time = datetime.utcnow()
        
        try:
            if tool_call.name == "bash":
                result = await self._tool_bash(tool_call.arguments)
            elif tool_call.name == "read_file":
                result = await self._tool_read_file(tool_call.arguments)
            elif tool_call.name == "edit_file":
                result = await self._tool_edit_file(tool_call.arguments)
            elif tool_call.name == "list_dir":
                result = await self._tool_list_dir(tool_call.arguments)
            elif tool_call.name == "find_files":
                result = await self._tool_find_files(tool_call.arguments)
            elif tool_call.name == "run_tests":
                result = await self._tool_run_tests(tool_call.arguments)
            elif tool_call.name == "create_diff":
                result = await self._tool_create_diff(tool_call.arguments)
            elif tool_call.name == "submit_patch":
                result = await self._tool_submit_patch(tool_call.arguments)
            else:
                result = f"Unknown tool: {tool_call.name}"
            
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            # Record tool call
            self._tool_calls.append(ToolCallRecord(
                timestamp=start_time,
                tool_name=tool_call.name,
                arguments=tool_call.arguments,
                result={"output": result[:1000]},
                duration_ms=duration_ms,
            ))
            
            return result
        
        except Exception as e:
            logger.error("Tool execution failed", tool=tool_call.name, error=str(e))
            return f"Error: {str(e)}"
    
    async def _tool_bash(self, args: dict[str, Any]) -> str:
        """Execute bash command."""
        command = args.get("command", "")
        timeout = args.get("timeout", 300)
        cwd = args.get("cwd")
        
        result = await self.sandbox.bash(command, timeout=timeout, cwd=cwd)
        
        output = f"Exit code: {result.exit_code}\n"
        if result.stdout:
            output += f"STDOUT:\n{result.stdout}\n"
        if result.stderr:
            output += f"STDERR:\n{result.stderr}\n"
        if result.truncated:
            output += "[Output truncated]\n"
        if result.timeout:
            output += "[Command timed out]\n"
        
        return output
    
    async def _tool_read_file(self, args: dict[str, Any]) -> str:
        """Read file contents."""
        file_path = args.get("file_path", "")
        start_line = args.get("start_line")
        end_line = args.get("end_line")
        
        try:
            content = await self.sandbox.read_file(file_path, start_line, end_line)
            return content
        except FileNotFoundError as e:
            return f"Error: {str(e)}"
    
    async def _tool_edit_file(self, args: dict[str, Any]) -> str:
        """Edit a file."""
        from ssr_studio.sandbox import EditOperation
        
        file_path = args.get("file_path", "")
        operation = args.get("operation", "replace")
        
        # Don't allow editing test files
        if any(test_file in file_path for test_file in self.artifact.test_files):
            return "Error: Cannot edit test files. Only source code can be modified."
        
        op_args = {}
        if operation == "replace":
            op_args["content"] = args.get("content", "")
        elif operation == "search_replace":
            op_args["old_text"] = args.get("old_text", "")
            op_args["new_text"] = args.get("new_text", "")
        elif operation == "insert":
            op_args["line"] = args.get("line", 1)
            op_args["text"] = args.get("text", "")
        elif operation == "delete":
            op_args["start_line"] = args.get("start_line", 1)
            op_args["end_line"] = args.get("end_line", args.get("start_line", 1))
        elif operation == "apply_diff":
            op_args["diff"] = args.get("diff", "")
        
        edit_op = EditOperation(type=operation, file_path=file_path, args=op_args)
        results = await self.sandbox.edit([edit_op])
        
        if results and results[0].success:
            return f"Successfully edited {file_path}"
        else:
            error = results[0].error if results else "Unknown error"
            return f"Edit failed: {error}"
    
    async def _tool_list_dir(self, args: dict[str, Any]) -> str:
        """List directory contents."""
        path = args.get("path", ".")
        
        try:
            entries = await self.sandbox.list_dir(path)
            lines = []
            for entry in entries:
                type_indicator = "/" if entry["type"] == "directory" else ""
                lines.append(f"{entry['name']}{type_indicator}")
            return "\n".join(lines) if lines else "(empty directory)"
        except FileNotFoundError as e:
            return f"Error: {str(e)}"
    
    async def _tool_find_files(self, args: dict[str, Any]) -> str:
        """Find files matching pattern."""
        pattern = args.get("pattern", "*")
        path = args.get("path", ".")
        
        files = await self.sandbox.find_files(pattern, path)
        return "\n".join(files) if files else "(no files found)"
    
    async def _tool_run_tests(self, args: dict[str, Any]) -> str:
        """Run the test suite."""
        # Run test script with parser
        result = await self.sandbox.bash(
            "bash test_script.sh 2>&1 | python test_parser.py",
            timeout=self.artifact.metadata.max_test_runtime_sec + 30,
        )
        
        if result.exit_code != 0 and not result.stdout.strip():
            return f"Test execution failed:\n{result.stderr}"
        
        try:
            test_results = json.loads(result.stdout.strip())
            
            passed = sum(1 for s in test_results.values() if s == "passed")
            failed = sum(1 for s in test_results.values() if s == "failed")
            total = len(test_results)
            
            summary = f"Test Results: {passed}/{total} passed, {failed} failed\n\n"
            
            # Show failing tests
            if failed > 0:
                summary += "Failing tests:\n"
                for test_id, status in test_results.items():
                    if status == "failed":
                        summary += f"  - {test_id}\n"
            
            return summary
        
        except json.JSONDecodeError:
            return f"Could not parse test results:\n{result.stdout[:500]}"
    
    async def _tool_create_diff(self, args: dict[str, Any]) -> str:
        """Create a diff of all changes."""
        diff = await self.sandbox.create_diff("ssr-buggy")
        
        if not diff.strip():
            return "No changes made yet."
        
        return f"Current changes:\n```diff\n{diff}\n```"
    
    async def _tool_submit_patch(self, args: dict[str, Any]) -> str:
        """Submit the fix patch."""
        patch = args.get("patch")
        patch_file = args.get("patch_file")
        
        if patch:
            self._pred_patch = patch
        elif patch_file:
            try:
                self._pred_patch = await self.sandbox.read_file(patch_file)
            except Exception as e:
                return f"Error reading patch file: {e}"
        else:
            # Generate diff from current state
            self._pred_patch = await self.sandbox.create_diff("ssr-buggy")
        
        if not self._pred_patch or not self._pred_patch.strip():
            return "Error: Empty patch. Make some changes first."
        
        self._submitted = True
        
        return (
            f"Patch submitted successfully!\n"
            f"Your patch will now be evaluated against the oracle tests.\n"
            f"Patch size: {len(self._pred_patch)} bytes"
        )
    
    def get_tool_calls(self) -> list[ToolCallRecord]:
        """Get all tool calls made during solving."""
        return self._tool_calls
    
    def get_messages(self) -> list[Message]:
        """Get the conversation history."""
        return self._messages
    
    def get_patch(self) -> str | None:
        """Get the predicted patch."""
        return self._pred_patch
