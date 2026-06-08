"""Built-in Skill: File Operations — read, write, list files."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from kiracode.skills.registry import SkillMeta

skill_meta = SkillMeta(
    name="file_ops",
    description="Read, write, and list files in the project directory",
    tags=["file", "io", "read", "write"],
    capabilities=["file_read", "file_write"],
    source="builtin",
)

# All file operations are restricted to this directory
ALLOWED_ROOT = Path("D:/agent/agent-project-codex-7")


def _check_path(path: str) -> Path:
    """Resolve and validate that path is within ALLOWED_ROOT."""
    p = Path(path).resolve()
    root = ALLOWED_ROOT.resolve()
    if not str(p).startswith(str(root)):
        raise PermissionError(f"Path {path} is outside allowed directory {root}")
    return p


class SkillClass:
    """File operations skill."""

    async def execute(self, action: str, path: str, content: str = "") -> dict[str, Any]:
        try:
            p = _check_path(path)
        except PermissionError as e:
            return {"success": False, "error": str(e)}

        if action == "read":
            if not p.exists():
                return {"success": False, "error": f"File not found: {path}"}
            text = p.read_text(encoding="utf-8", errors="replace")
            return {"success": True, "content": text, "lines": len(text.split("\n"))}
        elif action == "write":
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return {"success": True, "bytes_written": len(content.encode("utf-8"))}
        elif action == "list":
            if p.is_dir():
                items = [f.name for f in p.iterdir()]
                return {"success": True, "items": items, "count": len(items)}
            return {"success": False, "error": f"Not a directory: {path}"}
        else:
            return {"success": False, "error": f"Unknown action: {action}"}
