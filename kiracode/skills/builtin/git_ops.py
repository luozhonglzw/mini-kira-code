"""Built-in Skill: Git Operations — status, diff, commit via subprocess."""

from __future__ import annotations

from typing import Any

from kiracode.security.sandbox import Sandbox, SandboxConfig
from kiracode.skills.registry import SkillMeta

skill_meta = SkillMeta(
    name="git_ops",
    description="Git operations: status, diff, log, commit",
    tags=["git", "version control", "commit", "diff"],
    capabilities=["git_ops"],
    source="builtin",
)


class SkillClass:
    """Git operations skill."""

    def __init__(self) -> None:
        self._sandbox = Sandbox(SandboxConfig(timeout=15))

    async def execute(self, action: str, args: str = "") -> dict[str, Any]:
        cmd_map = {
            "status": "git status --short",
            "diff": "git diff",
            "log": "git log --oneline -10",
            "branch": "git branch -a",
        }
        cmd = cmd_map.get(action)
        if cmd is None:
            return {"success": False, "error": f"Unknown git action: {action}"}

        if args:
            cmd = f"{cmd} {args}"

        result = await self._sandbox.run_command(["bash", "-c", cmd])
        return {
            "success": result.success,
            "output": result.stdout.strip(),
            "error": result.stderr.strip() if result.stderr else "",
        }
