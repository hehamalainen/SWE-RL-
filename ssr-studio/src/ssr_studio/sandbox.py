"""
Sandbox runner for SSR Studio.

Provides secure Docker-based execution environment for SSR episodes.
Implements the security requirements from the PRD:
- No outbound network access by default
- CPU/memory/time quotas
- Read/write isolation per episode
- Non-root execution
"""

import asyncio
import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import docker
from docker.errors import ContainerError, ImageNotFound, APIError
from docker.models.containers import Container

from ssr_studio.config import settings
import structlog

logger = structlog.get_logger()


@dataclass
class BashResult:
    """Result of a bash command execution."""
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    truncated: bool = False
    timeout: bool = False


@dataclass
class EditOperation:
    """A file edit operation."""
    type: str  # "replace", "insert", "delete", "apply_diff", "search_replace"
    file_path: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class EditResult:
    """Result of a file edit operation."""
    success: bool
    file_path: str
    error: str | None = None
    lines_changed: int = 0


class Sandbox:
    """
    Secure sandbox environment for running SSR episodes.
    
    Each sandbox is an ephemeral Docker container with:
    - No network access (by default)
    - CPU and memory limits
    - Writable overlay filesystem
    - Non-root execution
    """
    
    def __init__(
        self,
        image_ref: str,
        sandbox_id: UUID | None = None,
        work_dir: str = "/workspace",
        network_enabled: bool | None = None,
        cpu_limit: float | None = None,
        memory_limit: str | None = None,
    ):
        self.image_ref = image_ref
        self.sandbox_id = sandbox_id or uuid4()
        self.work_dir = work_dir
        self.network_enabled = network_enabled if network_enabled is not None else settings.sandbox_network_enabled
        self.cpu_limit = cpu_limit or settings.sandbox_cpu_limit
        self.memory_limit = memory_limit or settings.sandbox_memory_limit
        
        self._client: docker.DockerClient | None = None
        self._container: Container | None = None
        self._temp_dir: Path | None = None
        self._started = False
    
    @property
    def container_name(self) -> str:
        """Get the container name."""
        return f"ssr-sandbox-{self.sandbox_id}"
    
    async def start(self) -> None:
        """Start the sandbox container."""
        if self._started:
            return
        
        logger.info("Starting sandbox", sandbox_id=str(self.sandbox_id), image=self.image_ref)
        
        # Initialize Docker client
        self._client = docker.from_env()
        
        # Create temp directory for file transfers
        self._temp_dir = Path(tempfile.mkdtemp(prefix=f"ssr-{self.sandbox_id}-"))
        
        # Prepare container configuration
        container_config = {
            "image": self.image_ref,
            "name": self.container_name,
            "detach": True,
            "tty": True,
            "stdin_open": True,
            "working_dir": self.work_dir,
            "command": "/bin/bash",
            # Resource limits
            "cpu_period": 100000,
            "cpu_quota": int(self.cpu_limit * 100000),
            "mem_limit": self.memory_limit,
            # Security
            "security_opt": ["no-new-privileges:true"],
            "cap_drop": ["ALL"],
            "cap_add": ["CHOWN", "SETUID", "SETGID", "DAC_OVERRIDE", "FOWNER"],
            # Labels for identification
            "labels": {
                "ssr.sandbox_id": str(self.sandbox_id),
                "ssr.created_at": datetime.utcnow().isoformat(),
            },
        }
        
        # Network isolation
        if not self.network_enabled:
            container_config["network_mode"] = "none"
        
        # Create and start container
        try:
            self._container = await asyncio.to_thread(
                self._client.containers.run,
                **container_config,
            )
            self._started = True
            logger.info("Sandbox started", container_id=self._container.id[:12])
        except ImageNotFound:
            raise RuntimeError(f"Docker image not found: {self.image_ref}")
        except APIError as e:
            raise RuntimeError(f"Failed to start sandbox: {e}")
    
    async def stop(self) -> None:
        """Stop and remove the sandbox container."""
        if not self._started:
            return
        
        logger.info("Stopping sandbox", sandbox_id=str(self.sandbox_id))
        
        try:
            if self._container:
                await asyncio.to_thread(self._container.stop, timeout=10)
                await asyncio.to_thread(self._container.remove, force=True)
        except Exception as e:
            logger.warning("Error stopping container", error=str(e))
        
        # Clean up temp directory
        if self._temp_dir and self._temp_dir.exists():
            shutil.rmtree(self._temp_dir, ignore_errors=True)
        
        self._started = False
        self._container = None
    
    async def bash(
        self,
        command: str,
        timeout: int | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> BashResult:
        """
        Execute a bash command in the sandbox.
        
        Args:
            command: The bash command to execute
            timeout: Command timeout in seconds (default from settings)
            cwd: Working directory for the command
            env: Additional environment variables
        
        Returns:
            BashResult with exit code, stdout, stderr, and timing
        """
        if not self._started or not self._container:
            raise RuntimeError("Sandbox not started")
        
        timeout = timeout or settings.sandbox_bash_timeout
        cwd = cwd or self.work_dir
        
        # Build the full command
        full_command = f"cd {cwd} && {command}"
        
        # Prepare environment
        env_str = ""
        if env:
            env_str = " ".join(f"{k}={v}" for k, v in env.items()) + " "
        
        exec_command = ["bash", "-c", f"{env_str}{full_command}"]
        
        start_time = datetime.utcnow()
        
        try:
            # Execute with timeout
            exec_result = await asyncio.wait_for(
                asyncio.to_thread(
                    self._container.exec_run,
                    exec_command,
                    workdir=cwd,
                    demux=True,
                ),
                timeout=timeout,
            )
            
            end_time = datetime.utcnow()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            
            stdout_raw, stderr_raw = exec_result.output
            stdout = (stdout_raw or b"").decode("utf-8", errors="replace")
            stderr = (stderr_raw or b"").decode("utf-8", errors="replace")
            
            # Truncate if too large
            max_size = 50000  # 50KB per stream
            truncated = False
            if len(stdout) > max_size:
                stdout = stdout[:max_size] + "\n... [truncated]"
                truncated = True
            if len(stderr) > max_size:
                stderr = stderr[:max_size] + "\n... [truncated]"
                truncated = True
            
            return BashResult(
                exit_code=exec_result.exit_code,
                stdout=stdout,
                stderr=stderr,
                duration_ms=duration_ms,
                truncated=truncated,
            )
        
        except asyncio.TimeoutError:
            end_time = datetime.utcnow()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)
            
            return BashResult(
                exit_code=-1,
                stdout="",
                stderr=f"Command timed out after {timeout}s",
                duration_ms=duration_ms,
                timeout=True,
            )
        
        except Exception as e:
            return BashResult(
                exit_code=-1,
                stdout="",
                stderr=f"Execution error: {str(e)}",
                duration_ms=0,
            )
    
    async def read_file(
        self,
        file_path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> str:
        """
        Read a file from the sandbox.
        
        Args:
            file_path: Path to the file (relative to work_dir or absolute)
            start_line: Starting line number (1-indexed, optional)
            end_line: Ending line number (1-indexed, optional)
        
        Returns:
            File contents (or specified lines)
        """
        if not file_path.startswith("/"):
            file_path = f"{self.work_dir}/{file_path}"
        
        if start_line is not None and end_line is not None:
            # Use sed to extract specific lines
            result = await self.bash(f"sed -n '{start_line},{end_line}p' {file_path}")
        else:
            result = await self.bash(f"cat {file_path}")
        
        if result.exit_code != 0:
            raise FileNotFoundError(f"Cannot read file: {file_path}\n{result.stderr}")
        
        return result.stdout
    
    async def write_file(self, file_path: str, content: str) -> None:
        """
        Write content to a file in the sandbox.
        
        Args:
            file_path: Path to the file (relative to work_dir or absolute)
            content: Content to write
        """
        if not file_path.startswith("/"):
            file_path = f"{self.work_dir}/{file_path}"
        
        # Ensure parent directory exists
        parent_dir = os.path.dirname(file_path)
        await self.bash(f"mkdir -p {parent_dir}")
        
        # Write content using heredoc
        # Escape content for bash
        escaped_content = content.replace("\\", "\\\\").replace("'", "'\"'\"'")
        
        result = await self.bash(f"cat > {file_path} << 'SSREOF'\n{content}\nSSREOF")
        
        if result.exit_code != 0:
            raise IOError(f"Cannot write file: {file_path}\n{result.stderr}")
    
    async def edit(self, operations: list[EditOperation]) -> list[EditResult]:
        """
        Apply edit operations to files in the sandbox.
        
        Supports: replace, insert, delete, apply_diff, search_replace
        """
        results = []
        
        for op in operations:
            file_path = op.file_path
            if not file_path.startswith("/"):
                file_path = f"{self.work_dir}/{file_path}"
            
            try:
                if op.type == "replace":
                    # Replace entire file content
                    await self.write_file(file_path, op.args["content"])
                    results.append(EditResult(success=True, file_path=file_path))
                
                elif op.type == "apply_diff":
                    # Apply a unified diff patch
                    diff_content = op.args["diff"]
                    # Write diff to temp file
                    temp_diff = f"/tmp/patch_{uuid4().hex[:8]}.diff"
                    await self.write_file(temp_diff, diff_content)
                    
                    # Apply the patch
                    result = await self.bash(f"patch -p1 < {temp_diff}", cwd=self.work_dir)
                    
                    if result.exit_code != 0:
                        results.append(EditResult(
                            success=False,
                            file_path=file_path,
                            error=f"Patch failed: {result.stderr}",
                        ))
                    else:
                        results.append(EditResult(success=True, file_path=file_path))
                
                elif op.type == "search_replace":
                    # Search and replace in file
                    old_text = op.args["old_text"]
                    new_text = op.args["new_text"]
                    
                    # Read file, replace, write back
                    content = await self.read_file(file_path)
                    new_content = content.replace(old_text, new_text)
                    await self.write_file(file_path, new_content)
                    
                    lines_changed = content.count(old_text)
                    results.append(EditResult(
                        success=True,
                        file_path=file_path,
                        lines_changed=lines_changed,
                    ))
                
                elif op.type == "insert":
                    # Insert text at line
                    line_num = op.args["line"]
                    text = op.args["text"]
                    
                    result = await self.bash(
                        f"sed -i '{line_num}i\\{text}' {file_path}"
                    )
                    
                    if result.exit_code != 0:
                        results.append(EditResult(
                            success=False,
                            file_path=file_path,
                            error=result.stderr,
                        ))
                    else:
                        results.append(EditResult(success=True, file_path=file_path))
                
                elif op.type == "delete":
                    # Delete lines from file
                    start_line = op.args["start_line"]
                    end_line = op.args.get("end_line", start_line)
                    
                    result = await self.bash(
                        f"sed -i '{start_line},{end_line}d' {file_path}"
                    )
                    
                    if result.exit_code != 0:
                        results.append(EditResult(
                            success=False,
                            file_path=file_path,
                            error=result.stderr,
                        ))
                    else:
                        results.append(EditResult(
                            success=True,
                            file_path=file_path,
                            lines_changed=end_line - start_line + 1,
                        ))
                
                else:
                    results.append(EditResult(
                        success=False,
                        file_path=file_path,
                        error=f"Unknown operation type: {op.type}",
                    ))
            
            except Exception as e:
                results.append(EditResult(
                    success=False,
                    file_path=file_path,
                    error=str(e),
                ))
        
        return results
    
    async def list_dir(self, path: str = ".") -> list[dict[str, Any]]:
        """
        List directory contents.
        
        Returns list of dicts with name, type, size for each entry.
        """
        if not path.startswith("/"):
            path = f"{self.work_dir}/{path}"
        
        result = await self.bash(f"ls -la {path}")
        
        if result.exit_code != 0:
            raise FileNotFoundError(f"Cannot list directory: {path}\n{result.stderr}")
        
        entries = []
        for line in result.stdout.strip().split("\n")[1:]:  # Skip "total" line
            parts = line.split()
            if len(parts) >= 9:
                entry_type = "directory" if parts[0].startswith("d") else "file"
                name = " ".join(parts[8:])
                if name not in [".", ".."]:
                    entries.append({
                        "name": name,
                        "type": entry_type,
                        "size": int(parts[4]) if parts[4].isdigit() else 0,
                        "permissions": parts[0],
                    })
        
        return entries
    
    async def find_files(self, pattern: str, path: str = ".") -> list[str]:
        """
        Find files matching a pattern.
        
        Args:
            pattern: Glob pattern (e.g., "*.py", "test_*.py")
            path: Starting path for search
        
        Returns:
            List of matching file paths (relative to work_dir)
        """
        if not path.startswith("/"):
            path = f"{self.work_dir}/{path}"
        
        result = await self.bash(f"find {path} -name '{pattern}' -type f 2>/dev/null")
        
        if result.exit_code != 0 and result.stderr:
            return []
        
        files = [
            f.strip().replace(f"{self.work_dir}/", "")
            for f in result.stdout.strip().split("\n")
            if f.strip()
        ]
        
        return files
    
    async def git_init(self) -> None:
        """Initialize or reinitialize git repository (used for solver leak prevention)."""
        # Remove existing .git if present
        await self.bash("rm -rf .git")
        
        # Initialize fresh repo
        await self.bash("git init")
        await self.bash("git config user.email 'ssr@studio.local'")
        await self.bash("git config user.name 'SSR Studio'")
    
    async def git_tag(self, tag_name: str) -> None:
        """Create a git tag at current state."""
        await self.bash("git add -A")
        await self.bash("git commit -m 'SSR checkpoint' --allow-empty")
        await self.bash(f"git tag {tag_name}")
    
    async def git_restore_from_tag(self, tag_name: str, files: list[str]) -> None:
        """Restore specific files from a git tag."""
        for file_path in files:
            await self.bash(f"git checkout {tag_name} -- {file_path}")
    
    async def apply_diff(self, diff_content: str, reverse: bool = False) -> bool:
        """
        Apply a unified diff patch.
        
        Args:
            diff_content: The diff content to apply
            reverse: If True, apply the patch in reverse
        
        Returns:
            True if patch applied successfully
        """
        temp_diff = f"/tmp/patch_{uuid4().hex[:8]}.diff"
        await self.write_file(temp_diff, diff_content)
        
        reverse_flag = "-R" if reverse else ""
        result = await self.bash(f"patch -p1 {reverse_flag} < {temp_diff}")
        
        return result.exit_code == 0
    
    async def create_diff(self, base_tag: str = "HEAD") -> str:
        """Create a unified diff of all changes since a tag/commit."""
        result = await self.bash(f"git diff {base_tag}")
        return result.stdout
    
    async def get_image_digest(self) -> str | None:
        """Get the digest of the Docker image."""
        if not self._container:
            return None
        
        try:
            image = await asyncio.to_thread(
                self._client.images.get,
                self.image_ref,
            )
            return image.id
        except Exception:
            return None
    
    async def __aenter__(self) -> "Sandbox":
        """Context manager entry."""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        await self.stop()


class SandboxPool:
    """
    Pool of sandbox instances for parallel episode execution.
    
    Manages creation, reuse, and cleanup of sandbox containers.
    """
    
    def __init__(self, max_sandboxes: int = 10):
        self.max_sandboxes = max_sandboxes
        self._available: dict[str, list[Sandbox]] = {}
        self._in_use: set[UUID] = set()
        self._lock = asyncio.Lock()
    
    async def acquire(self, image_ref: str) -> Sandbox:
        """
        Acquire a sandbox for the given image.
        
        Returns a new or recycled sandbox instance.
        """
        async with self._lock:
            # Check for available sandbox with this image
            if image_ref in self._available and self._available[image_ref]:
                sandbox = self._available[image_ref].pop()
                self._in_use.add(sandbox.sandbox_id)
                return sandbox
            
            # Create new sandbox
            if len(self._in_use) >= self.max_sandboxes:
                raise RuntimeError("Maximum sandbox limit reached")
            
            sandbox = Sandbox(image_ref=image_ref)
            await sandbox.start()
            self._in_use.add(sandbox.sandbox_id)
            
            return sandbox
    
    async def release(self, sandbox: Sandbox, recycle: bool = False) -> None:
        """
        Release a sandbox back to the pool.
        
        Args:
            sandbox: The sandbox to release
            recycle: If True, keep the sandbox for reuse; otherwise destroy it
        """
        async with self._lock:
            self._in_use.discard(sandbox.sandbox_id)
            
            if recycle:
                # Add to available pool
                if sandbox.image_ref not in self._available:
                    self._available[sandbox.image_ref] = []
                self._available[sandbox.image_ref].append(sandbox)
            else:
                # Destroy the sandbox
                await sandbox.stop()
    
    async def cleanup(self) -> None:
        """Clean up all sandboxes in the pool."""
        async with self._lock:
            for sandboxes in self._available.values():
                for sandbox in sandboxes:
                    await sandbox.stop()
            self._available.clear()


# Global sandbox pool
sandbox_pool = SandboxPool()
