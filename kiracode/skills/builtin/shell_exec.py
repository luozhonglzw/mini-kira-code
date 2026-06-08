"""Built-in Skill: Shell Execution — run commands in sandbox."""

from __future__ import annotations

import sys
from typing import Any

from kiracode.security.sandbox import Sandbox, SandboxConfig
from kiracode.skills.registry import SkillMeta

skill_meta = SkillMeta(
    name="shell_exec",
    description="Execute shell commands in a sandboxed environment",
    tags=["shell", "command", "bash", "execute"],
    capabilities=["shell_exec"],
    source="builtin",
)

# All commands run inside this directory
WORK_DIR = "D:/agent/agent-project-codex-7"


class SkillClass:
    """Shell execution skill with sandbox isolation."""

    def __init__(self) -> None:
        self._sandbox = Sandbox(SandboxConfig(timeout=300))

    async def execute(self, command: str, timeout: int = 300) -> dict[str, Any]:
        self._sandbox.config.timeout = timeout
        # Use cmd.exe on Windows to avoid WSL bash issues
        if sys.platform == "win32":
            cmd = ["cmd.exe", "/c", command]
        else:
            cmd = ["bash", "-c", command]
        result = await self._sandbox.run_command(cmd, cwd=WORK_DIR)
        return {
            "success": result.success,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
            "duration_ms": result.duration_ms,
            "timed_out": result.timed_out,
            "error": result.error,
        }
