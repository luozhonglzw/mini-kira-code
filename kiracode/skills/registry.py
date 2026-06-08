"""Skill Registry — central registration and lookup for all skills.

Design decisions:
- Skills are registered by name with metadata (description, capabilities).
- Supports get/list/search operations.
- Skills are loaded via the Loader, registered here for runtime lookup.
- Registry is a singleton pattern (module-level instance).
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SkillMeta(BaseModel):
    name: str
    description: str = ""
    version: str = "1.0.0"
    author: str = ""
    tags: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    enabled: bool = True
    source: str = ""  # "builtin" | "plugin" | filepath


class SkillRegistry:
    """Central registry for all loaded skills."""

    def __init__(self) -> None:
        self._skills: dict[str, SkillMeta] = {}
        self._instances: dict[str, Any] = {}  # name → skill instance

    def register(self, meta: SkillMeta, instance: Any = None) -> None:
        """Register a skill with metadata and optional instance."""
        self._skills[meta.name] = meta
        if instance is not None:
            self._instances[meta.name] = instance
        logger.info("Registered skill: %s (source=%s)", meta.name, meta.source)

    def unregister(self, name: str) -> bool:
        removed = self._skills.pop(name, None)
        self._instances.pop(name, None)
        return removed is not None

    def get(self, name: str) -> SkillMeta | None:
        return self._skills.get(name)

    def get_instance(self, name: str) -> Any | None:
        return self._instances.get(name)

    def list_skills(self, enabled_only: bool = True) -> list[SkillMeta]:
        skills = list(self._skills.values())
        if enabled_only:
            skills = [s for s in skills if s.enabled]
        return skills

    def search(self, query: str) -> list[SkillMeta]:
        """Simple keyword search across name, description, tags, capabilities."""
        query_lower = query.lower()
        results = []
        for skill in self._skills.values():
            if not skill.enabled:
                continue
            searchable = f"{skill.name} {skill.description} {' '.join(skill.tags)} {' '.join(skill.capabilities)}".lower()
            if query_lower in searchable:
                results.append(skill)
        return results

    def summary(self) -> dict[str, Any]:
        return {
            "total": len(self._skills),
            "enabled": sum(1 for s in self._skills.values() if s.enabled),
            "by_source": {
                src: sum(1 for s in self._skills.values() if s.source == src)
                for src in set(s.source for s in self._skills.values())
            },
            "names": list(self._skills.keys()),
        }


# Module-level singleton
registry = SkillRegistry()
