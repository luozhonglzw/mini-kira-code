"""Skill Router — semantic routing to select the best skill for a query.

Design decisions:
- Uses keyword matching + capability scoring to route queries to skills.
- Falls back to registry search when no semantic model is available.
- Returns ranked list of (skill_name, score) pairs.
- Can be extended with embedding-based routing when RAG is available.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from kiracode.skills.registry import SkillMeta, SkillRegistry, registry


class RouteResult(BaseModel):
    skill_name: str
    score: float
    reason: str = ""


# ── Keyword → capability mapping ───────────────────────────────────────────

QUERY_KEYWORDS: dict[str, list[str]] = {
    "file_read": ["read", "open", "load", "file", "读取", "打开"],
    "file_write": ["write", "save", "create", "file", "写入", "保存", "创建"],
    "shell_exec": ["run", "execute", "command", "shell", "bash", "执行", "运行"],
    "git_ops": ["git", "commit", "push", "pull", "branch", "merge"],
    "code_search": ["search", "find", "grep", "lookup", "搜索", "查找"],
    "code_review": ["review", "check", "audit", "审查", "检查"],
    "test_run": ["test", "pytest", "unittest", "测试"],
    "security_scan": ["security", "vulnerability", "secret", "安全", "漏洞"],
    "screenshot_analyze": [
        "screenshot", "截图", "界面", "ui", "design", "设计稿",
        "参考这个", "实现这个界面", "图片", "image", "visual",
        "视觉", "页面", "page", "mockup", "prototype", "原型",
    ],
    "ui_analysis": ["组件", "component", "布局", "layout", "样式", "style"],
}


class SkillRouter:
    """Routes queries to the most appropriate skill."""

    def __init__(self, skill_registry: SkillRegistry | None = None) -> None:
        self._registry = skill_registry or registry

    def route(self, query: str, top_k: int = 3) -> list[RouteResult]:
        """Find the best matching skills for a query."""
        query_lower = query.lower()
        scores: dict[str, float] = {}
        reasons: dict[str, str] = {}

        for skill in self._registry.list_skills(enabled_only=True):
            score = 0.0
            reason_parts: list[str] = []

            # 1. Name match
            if skill.name.lower() in query_lower:
                score += 3.0
                reason_parts.append("name_match")

            # 2. Keyword match against capabilities
            for cap in skill.capabilities:
                keywords = QUERY_KEYWORDS.get(cap, [])
                for kw in keywords:
                    if kw in query_lower:
                        score += 1.5
                        reason_parts.append(f"cap:{cap}")
                        break

            # 3. Tag match
            for tag in skill.tags:
                if tag.lower() in query_lower:
                    score += 1.0
                    reason_parts.append(f"tag:{tag}")

            # 4. Description match
            desc_words = skill.description.lower().split()
            for word in desc_words:
                if len(word) > 3 and word in query_lower:
                    score += 0.5
                    reason_parts.append("desc_match")

            if score > 0:
                scores[skill.name] = score
                reasons[skill.name] = ", ".join(set(reason_parts))

        # Sort by score
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return [
            RouteResult(
                skill_name=name,
                score=round(score, 2),
                reason=reasons.get(name, ""),
            )
            for name, score in ranked
        ]

    def find_by_capability(self, capability: str) -> list[SkillMeta]:
        """Find all skills with a specific capability."""
        return [
            s for s in self._registry.list_skills()
            if capability in s.capabilities
        ]
