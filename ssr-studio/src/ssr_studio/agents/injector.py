"""
Bug Injector Agent for SSR Studio.

Implements the injector role from the SSR paper (§2.3, Appendix A.1):
- Explores repository to discover tests
- Creates test script and parser
- Injects bugs into code
- Weakens tests to hide the bug
- Produces a complete bug artifact
"""

import json
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import structlog

from ssr_studio.config import settings, InjectionStrategy
from ssr_studio.models import (
    ArtifactMetadata,
    BugArtifact,
    ToolCall as ToolCallRecord,
)
from ssr_studio.model_gateway import (
    ModelGateway,
    Message,
    Role,
    ToolCall,
    get_model_gateway,
)
from ssr_studio.sandbox import Sandbox, EditOperation
from ssr_studio.tools import INJECTOR_TOOLS

logger = structlog.get_logger()


# =============================================================================
# System Prompts (SSR paper Appendix A.1)
# =============================================================================

INJECTOR_SYSTEM_PROMPT = """You are an expert software engineer tasked with creating a bug artifact for training purposes.

Your goal is to:
1. Explore the repository and understand its structure
2. Discover how to run tests (pytest, unittest, npm test, go test, etc.)
3. Create a test script (test_script.sh) that runs the test suite
4. Create a test parser (test_parser.py) that parses test output into JSON
5. Inject a realistic bug into the code (NOT into test files)
6. Weaken the tests so the bug is not immediately caught

IMPORTANT RULES:
- The bug must be in CODE files, not test files
- Test weakening must only modify TEST files
- The bug should be subtle but detectable by tests
- After weakening, some tests should pass that would otherwise fail
- The test script must complete within {max_test_runtime_sec} seconds

INJECTION STRATEGY: {injection_strategy}
{strategy_instructions}

ARTIFACT REQUIREMENTS:
1. test_script.sh - Bash script that runs tests and outputs to stdout
2. test_files.txt - List of test file paths (one per line)
3. test_parser.py - Python script that reads stdin and outputs JSON mapping:
   {{"test_name": "passed"|"failed", ...}}
4. bug_inject.diff - Unified diff that introduces the bug (code only)
5. test_weaken.diff - Unified diff that weakens tests (test files only)

When ready, use the submit_artifact tool with all five components.
"""

STRATEGY_INSTRUCTIONS = {
    InjectionStrategy.DIRECT: """
DIRECT INJECTION:
- Introduce a bug by modifying existing code logic
- Make subtle changes like off-by-one errors, wrong operators, missing checks
- The bug should cause test failures that can be hidden by weakening tests
""",
    InjectionStrategy.REMOVAL_ONLY: """
REMOVAL-ONLY INJECTION:
- Inject bugs ONLY by removing code (deleting lines, functions, or conditions)
- Do NOT add new code; only remove existing code
- Remove important checks, validations, or logic
- The repository must still be runnable after removal
""",
    InjectionStrategy.HISTORY_AWARE: """
HISTORY-AWARE INJECTION:
- First check git history for past bugs or reverted commits
- Use 'git log --oneline' and 'git show <commit>' to find interesting changes
- Revert a previous fix to reintroduce an old bug
- Or combine removal with historical context
""",
}


class InjectorAgent:
    """
    Bug injection agent that creates SSR-compliant artifacts.
    
    The agent explores a repository, discovers tests, and creates
    a bug artifact consisting of:
    - test_script.sh
    - test_files.txt  
    - test_parser.py
    - bug_inject.diff
    - test_weaken.diff
    """
    
    def __init__(
        self,
        sandbox: Sandbox,
        env_id: UUID,
        strategy: InjectionStrategy = InjectionStrategy.REMOVAL_ONLY,
        model_gateway: ModelGateway | None = None,
        min_passing_tests: int | None = None,
        min_changed_files: int | None = None,
        min_failing_tests: int | None = None,
        max_test_runtime_sec: int | None = None,
    ):
        self.sandbox = sandbox
        self.env_id = env_id
        self.strategy = strategy
        self.gateway = model_gateway or get_model_gateway()
        
        # Configuration
        self.min_passing_tests = min_passing_tests or settings.min_passing_tests
        self.min_changed_files = min_changed_files or settings.min_changed_files
        self.min_failing_tests = min_failing_tests or settings.min_failing_tests
        self.max_test_runtime_sec = max_test_runtime_sec or settings.max_test_runtime_sec
        
        # State
        self._messages: list[Message] = []
        self._tool_calls: list[ToolCallRecord] = []
        self._artifact: BugArtifact | None = None
        self._submitted = False
    
    def _get_system_prompt(self) -> str:
        """Generate the system prompt with configuration."""
        return INJECTOR_SYSTEM_PROMPT.format(
            max_test_runtime_sec=self.max_test_runtime_sec,
            injection_strategy=self.strategy.value,
            strategy_instructions=STRATEGY_INSTRUCTIONS[self.strategy],
        )
    
    async def run(self, max_steps: int = 50) -> BugArtifact | None:
        """
        Run the injection agent to produce a bug artifact.
        
        Args:
            max_steps: Maximum number of tool-use steps
        
        Returns:
            BugArtifact if successful, None otherwise
        """
        logger.info(
            "Starting injection agent",
            strategy=self.strategy.value,
            max_steps=max_steps,
        )
        
        # Initialize conversation
        self._messages = [
            Message(role=Role.SYSTEM, content=self._get_system_prompt()),
            Message(
                role=Role.USER,
                content="Please explore this repository and create a bug artifact. "
                        "Start by understanding the project structure and test setup.",
            ),
        ]
        
        for step in range(max_steps):
            if self._submitted:
                break
            
            logger.info("Injection step", step=step + 1, max_steps=max_steps)
            
            # Generate next action
            result = await self.gateway.generate(
                role="injector",
                messages=self._messages,
                tools=INJECTOR_TOOLS,
            )
            
            # Handle response
            if result.tool_calls:
                # Execute tool calls
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
                # No tool calls - just add the response and continue
                if result.content:
                    self._messages.append(Message(
                        role=Role.ASSISTANT,
                        content=result.content,
                    ))
                    
                    # Prompt to continue
                    self._messages.append(Message(
                        role=Role.USER,
                        content="Please continue with the next step. "
                                "Use tools to explore the repo or create the artifact.",
                    ))
        
        return self._artifact
    
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
            elif tool_call.name == "submit_artifact":
                result = await self._tool_submit_artifact(tool_call.arguments)
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
        file_path = args.get("file_path", "")
        operation = args.get("operation", "replace")
        
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
    
    async def _tool_submit_artifact(self, args: dict[str, Any]) -> str:
        """Submit the bug artifact."""
        test_script = args.get("test_script", "")
        test_files = args.get("test_files", [])
        test_parser = args.get("test_parser", "")
        bug_inject_diff = args.get("bug_inject_diff", "")
        test_weaken_diff = args.get("test_weaken_diff", "")
        
        # Validate required fields
        missing = []
        if not test_script:
            missing.append("test_script")
        if not test_files:
            missing.append("test_files")
        if not test_parser:
            missing.append("test_parser")
        if not bug_inject_diff:
            missing.append("bug_inject_diff")
        if not test_weaken_diff:
            missing.append("test_weaken_diff")
        
        if missing:
            return f"Missing required fields: {', '.join(missing)}"
        
        # Create artifact
        metadata = ArtifactMetadata(
            artifact_id=uuid4(),
            env_id=self.env_id,
            injection_strategy=self.strategy,
            min_passing_tests=self.min_passing_tests,
            min_changed_files=self.min_changed_files,
            min_failing_tests=self.min_failing_tests,
            max_test_runtime_sec=self.max_test_runtime_sec,
            created_by_model=self.gateway.provider_name,
        )
        
        self._artifact = BugArtifact(
            metadata=metadata,
            test_script=test_script,
            test_files=test_files,
            test_parser=test_parser,
            bug_inject_diff=bug_inject_diff,
            test_weaken_diff=test_weaken_diff,
        )
        
        self._submitted = True
        
        return (
            f"Artifact submitted successfully!\n"
            f"Artifact ID: {metadata.artifact_id}\n"
            f"Test files: {len(test_files)}\n"
            f"This artifact will now be validated."
        )
    
    def get_tool_calls(self) -> list[ToolCallRecord]:
        """Get all tool calls made during injection."""
        return self._tool_calls
    
    def get_messages(self) -> list[Message]:
        """Get the conversation history."""
        return self._messages
