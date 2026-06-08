"""Sandbox — subprocess-isolated code execution.

Design decisions:
- Runs code in a subprocess with resource limits (timeout, memory).
- Captures stdout/stderr separately.
- Returns structured SandboxResult with exit code, output, and timing.
- On Windows, uses job objects concept via subprocess; on Unix, uses
  resource limits (RLIMIT). For now, timeout-based isolation only.
"""

from __future__ import annotations

import asyncio
import logging
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
    """Executes Python code in an isolated subprocess."""

    def __init__(self, config: SandboxConfig | None = None) -> None:
        self.config = config or SandboxConfig()

    async def run_code(self, code: str, args: list[str] | None = None) -> SandboxResult:
        """Execute Python code string in a subprocess."""
        start = time.monotonic()

        # Write code to a temp file
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

    async def run_command(self, command: list[str], cwd: str | None = None) -> SandboxResult:
        """Execute a shell command in a subprocess."""
        start = time.monotonic()
        return await self._run_subprocess(command, start, cwd=cwd)

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
