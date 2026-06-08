"""Built-in Skill: Code Search — grep-like code search with context."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from kiracode.skills.registry import SkillMeta

skill_meta = SkillMeta(
    name="code_search",
    description="Search for patterns in code files with context lines",
    tags=["search", "grep", "find", "code"],
    capabilities=["code_search"],
    source="builtin",
)


class SkillClass:
    """Code search skill — regex search across project files."""

    async def execute(
        self,
        pattern: str,
        directory: str = ".",
        glob: str = "*.py",
        context_lines: int = 2,
        max_results: int = 50,
    ) -> dict[str, Any]:
        d = Path(directory)
        if not d.exists():
            return {"success": False, "error": f"Directory not found: {directory}"}

        regex = re.compile(pattern)
        matches: list[dict[str, Any]] = []

        for filepath in d.rglob(glob):
            if not filepath.is_file():
                continue
            try:
                lines = filepath.read_text(encoding="utf-8", errors="replace").split("\n")
            except Exception:
                continue

            for i, line in enumerate(lines):
                if regex.search(line):
                    start = max(0, i - context_lines)
                    end = min(len(lines), i + context_lines + 1)
                    matches.append({
                        "file": str(filepath),
                        "line": i + 1,
                        "match": line.strip(),
                        "context": lines[start:end],
                    })
                    if len(matches) >= max_results:
                        return {"success": True, "matches": matches, "truncated": True}

        return {"success": True, "matches": matches, "truncated": False}
