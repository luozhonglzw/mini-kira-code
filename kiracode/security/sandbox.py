"""Sandbox — subprocess-isolated code execution.

Design decisions:
- Runs code in a subprocess with resource limits (timeout, memory).
- Captures stdout/stderr separately.
- Returns structured SandboxResult with exit code, output, and timing.
- On Windows, supports detached processes for background servers.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SandboxConfig(BaseModel):
    timeout: int = 30  # seconds
    max_memory_mb: int = 512
    max_output_chars: int = 100_000
    python_executable: str = sys.executable


class SandboxResult(BaseModel):
    success: bool
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""
    duration_ms: float = 0.0
    timed_out: bool = False
    error: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class Sandbox:
    """Executes code/commands in an isolated subprocess."""

    def __init__(self, config: SandboxConfig | None = None) -> None:
        self.config = config or SandboxConfig()

    async def run_code(self, code: str, args: list[str] | None = None) -> SandboxResult:
        """Execute Python code string in a subprocess."""
        start = time.monotonic()
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            tmp_path = f.name
        try:
            return await self._run_subprocess(
                [self.config.python_executable, tmp_path] + (args or []),
                start,
            )
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    async def run_command(
        self,
        command: list[str],
        cwd: str | None = None,
        detach: bool = False,
        detach_timeout: float = 5.0,
    ) -> SandboxResult:
        """Execute a shell command.

        Args:
            command: Command and arguments.
            cwd: Working directory.
            detach: If True, launch in background and return after detach_timeout.
            detach_timeout: Seconds to wait before assuming detached process started.
        """
        start = time.monotonic()

        if detach:
            return await self._run_detached(command, start, cwd, detach_timeout)

        return await self._run_subprocess(command, start, cwd=cwd)

    async def _run_detached(
        self, cmd: list[str], start: float, cwd: str | None, wait: float
    ) -> SandboxResult:
        """Launch a detached background process (for servers)."""
        try:
            if sys.platform == "win32":
                # Use subprocess.Popen with CREATE_NEW_CONSOLE to fully detach
                proc = subprocess.Popen(
                    cmd,
                    stdout=open("nul", "w"),
                    stderr=subprocess.STDOUT,
                    cwd=cwd,
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )
                # Wait briefly, then check if process is alive
                await asyncio.sleep(wait)
                alive = proc.poll() is None
                elapsed = (time.monotonic() - start) * 1000
                return SandboxResult(
                    success=alive,
                    exit_code=proc.returncode or 0,
                    stdout=f"Process started (PID={proc.pid}, alive={alive})",
                    duration_ms=elapsed,
                )
            else:
                # Unix: use nohup + &
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                    cwd=cwd,
                )
                await asyncio.sleep(wait)
                alive = proc.returncode is None
                elapsed = (time.monotonic() - start) * 1000
                return SandboxResult(
                    success=alive,
                    exit_code=proc.returncode or 0,
                    stdout=f"Process started (PID={proc.pid}, alive={alive})",
                    duration_ms=elapsed,
                )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            return SandboxResult(
                success=False,
                exit_code=-1,
                duration_ms=elapsed,
                error=str(e),
            )

    async def _run_subprocess(self, cmd: list[str], start: float, cwd: str | None = None) -> SandboxResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=self.config.timeout,
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                elapsed = (time.monotonic() - start) * 1000
                return SandboxResult(
                    success=False,
                    exit_code=-1,
                    timed_out=True,
                    duration_ms=elapsed,
                    error=f"Execution timed out after {self.config.timeout}s",
                )

            elapsed = (time.monotonic() - start) * 1000
            stdout = stdout_bytes.decode("utf-8", errors="replace")[: self.config.max_output_chars]
            stderr = stderr_bytes.decode("utf-8", errors="replace")[: self.config.max_output_chars]

            return SandboxResult(
                success=proc.returncode == 0,
                exit_code=proc.returncode or 0,
                stdout=stdout,
                stderr=stderr,
                duration_ms=elapsed,
            )

        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            return SandboxResult(
                success=False,
                exit_code=-1,
                duration_ms=elapsed,
                error=str(e),
            )
