"""Plugin-based Skill system with dynamic loading."""

from kiracode.skills.loader import SkillLoader
from kiracode.skills.registry import SkillMeta, SkillRegistry, registry
from kiracode.skills.router import RouteResult, SkillRouter

__all__ = [
    "SkillRegistry",
    "SkillMeta",
    "registry",
    "SkillLoader",
    "SkillRouter",
    "RouteResult",
]
