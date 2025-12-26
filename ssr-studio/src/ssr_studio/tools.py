"""
Tool definitions for SSR agents.

Defines the tools available to bug injector and solver agents,
matching the agent-computer interface from the SSR paper.
"""

from ssr_studio.model_gateway import ToolDefinition


# =============================================================================
# Common Tools (available to both injector and solver)
# =============================================================================

BASH_TOOL = ToolDefinition(
    name="bash",
    description="""Execute a bash command in the sandbox environment.
Use this to run shell commands, execute tests, install packages, etc.
The command runs in the workspace directory by default.
Output is truncated if too long.""",
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The bash command to execute",
            },
            "timeout": {
                "type": "integer",
                "description": "Command timeout in seconds (default: 300)",
            },
            "cwd": {
                "type": "string",
                "description": "Working directory for the command (default: workspace root)",
            },
        },
        "required": ["command"],
    },
)


READ_FILE_TOOL = ToolDefinition(
    name="read_file",
    description="""Read the contents of a file.
Can optionally read only a specific line range.
Use this to inspect source code, test files, configuration, etc.""",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the file (relative to workspace or absolute)",
            },
            "start_line": {
                "type": "integer",
                "description": "Starting line number (1-indexed, optional)",
            },
            "end_line": {
                "type": "integer",
                "description": "Ending line number (1-indexed, optional)",
            },
        },
        "required": ["file_path"],
    },
)


EDIT_FILE_TOOL = ToolDefinition(
    name="edit_file",
    description="""Edit a file by replacing, inserting, or deleting content.
Supports multiple operation types:
- replace: Replace entire file content
- search_replace: Find and replace text
- insert: Insert text at a specific line
- delete: Delete a range of lines
- apply_diff: Apply a unified diff patch""",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the file to edit",
            },
            "operation": {
                "type": "string",
                "enum": ["replace", "search_replace", "insert", "delete", "apply_diff"],
                "description": "Type of edit operation",
            },
            "content": {
                "type": "string",
                "description": "New content (for replace operation)",
            },
            "old_text": {
                "type": "string",
                "description": "Text to find (for search_replace)",
            },
            "new_text": {
                "type": "string",
                "description": "Replacement text (for search_replace)",
            },
            "line": {
                "type": "integer",
                "description": "Line number (for insert)",
            },
            "text": {
                "type": "string",
                "description": "Text to insert (for insert)",
            },
            "start_line": {
                "type": "integer",
                "description": "Start line (for delete)",
            },
            "end_line": {
                "type": "integer",
                "description": "End line (for delete)",
            },
            "diff": {
                "type": "string",
                "description": "Unified diff content (for apply_diff)",
            },
        },
        "required": ["file_path", "operation"],
    },
)


LIST_DIR_TOOL = ToolDefinition(
    name="list_dir",
    description="""List the contents of a directory.
Returns file names, types (file/directory), and sizes.
Use this to explore the repository structure.""",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the directory (default: workspace root)",
            },
        },
        "required": [],
    },
)


FIND_FILES_TOOL = ToolDefinition(
    name="find_files",
    description="""Find files matching a glob pattern.
Use this to locate test files, source files, configuration files, etc.
Examples: "*.py", "test_*.py", "**/*.js" """,
    parameters={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Glob pattern to match (e.g., '*.py', 'test_*.py')",
            },
            "path": {
                "type": "string",
                "description": "Starting path for search (default: workspace root)",
            },
        },
        "required": ["pattern"],
    },
)


# =============================================================================
# Injector-Specific Tools
# =============================================================================

SUBMIT_ARTIFACT_TOOL = ToolDefinition(
    name="submit_artifact",
    description="""Submit the bug artifact for validation.
Call this when you have created all required artifact files:
- test_script.sh: Script to run tests
- test_files.txt: List of test file paths (one per line)
- test_parser.py: Python script to parse test output into JSON
- bug_inject.diff: Unified diff that introduces the bug (code only)
- test_weaken.diff: Unified diff that weakens tests (tests only)

The artifact will be validated against SSR consistency checks.""",
    parameters={
        "type": "object",
        "properties": {
            "test_script": {
                "type": "string",
                "description": "Contents of test_script.sh",
            },
            "test_files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of test file paths",
            },
            "test_parser": {
                "type": "string",
                "description": "Contents of test_parser.py",
            },
            "bug_inject_diff": {
                "type": "string",
                "description": "Unified diff that introduces the bug (code files only)",
            },
            "test_weaken_diff": {
                "type": "string",
                "description": "Unified diff that weakens tests (test files only)",
            },
        },
        "required": ["test_script", "test_files", "test_parser", "bug_inject_diff", "test_weaken_diff"],
    },
)


# =============================================================================
# Solver-Specific Tools
# =============================================================================

SUBMIT_PATCH_TOOL = ToolDefinition(
    name="submit_patch",
    description="""Submit your predicted fix patch.
Call this when you have identified and fixed the bug.
The patch should be a unified diff that, when applied,
makes all tests pass.

You can either provide the patch content directly,
or specify a file path containing the patch.""",
    parameters={
        "type": "object",
        "properties": {
            "patch": {
                "type": "string",
                "description": "Unified diff patch content",
            },
            "patch_file": {
                "type": "string",
                "description": "Path to a file containing the patch",
            },
        },
        "required": [],
    },
)


CREATE_DIFF_TOOL = ToolDefinition(
    name="create_diff",
    description="""Create a unified diff of all changes made so far.
Use this to see what changes you've made and to prepare your patch for submission.""",
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
)


RUN_TESTS_TOOL = ToolDefinition(
    name="run_tests",
    description="""Run the test suite and get results.
This runs the test_script.sh and parses output with test_parser.py.
Returns a summary of passed/failed tests.""",
    parameters={
        "type": "object",
        "properties": {
            "filter": {
                "type": "string",
                "description": "Optional: run only tests matching this pattern",
            },
        },
        "required": [],
    },
)


# =============================================================================
# Tool Sets for Each Role
# =============================================================================

INJECTOR_TOOLS = [
    BASH_TOOL,
    READ_FILE_TOOL,
    EDIT_FILE_TOOL,
    LIST_DIR_TOOL,
    FIND_FILES_TOOL,
    SUBMIT_ARTIFACT_TOOL,
]

SOLVER_TOOLS = [
    BASH_TOOL,
    READ_FILE_TOOL,
    EDIT_FILE_TOOL,
    LIST_DIR_TOOL,
    FIND_FILES_TOOL,
    RUN_TESTS_TOOL,
    CREATE_DIFF_TOOL,
    SUBMIT_PATCH_TOOL,
]
