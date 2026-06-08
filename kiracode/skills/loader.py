"""Skill Loader — discovers and loads skill modules from directories.

Design decisions:
- Scans configured directories for Python modules with a `skill_meta` attribute.
- Each skill module must expose:
  - skill_meta: SkillMeta (metadata)
  - SkillClass: the skill class (optional, for instantiation)
- Supports hot-reload by re-scanning directories.
- Errors in individual skills don't block loading of others.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any

from kiracode.skills.registry import SkillMeta, SkillRegistry, registry

logger = logging.getLogger(__name__)


def _load_module_from_path(filepath: Path) -> Any | None:
    """Load a Python module from a file path."""
    module_name = f"kiracode_skill_{filepath.stem}"
    try:
        spec = importlib.util.spec_from_file_location(module_name, str(filepath))
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    except Exception as e:
        logger.warning("Failed to load skill from %s: %s", filepath, e)
        return None


class SkillLoader:
    """Discovers and loads skills from configured directories."""

    def __init__(self, skill_registry: SkillRegistry | None = None) -> None:
        self._registry = skill_registry or registry

    def load_from_directory(self, directory: str | Path) -> int:
        """Load all skill modules from a directory. Returns count loaded."""
        d = Path(directory)
        if not d.exists() or not d.is_dir():
            logger.debug("Skill directory not found: %s", d)
            return 0

        loaded = 0
        for py_file in d.glob("*.py"):
            if py_file.name.startswith("_"):
                continue
            if self._load_single_skill(py_file):
                loaded += 1
        return loaded

    def load_from_directories(self, directories: list[str]) -> int:
        """Load skills from multiple directories."""
        total = 0
        for d in directories:
            total += self.load_from_directory(d)
        return total

    def reload_all(self) -> int:
        """Re-scan all registered skill sources and reload."""
        reloaded = 0
        for meta in list(self._registry.list_skills(enabled_only=False)):
            if meta.source and meta.source not in ("builtin", "plugin"):
                # It's a file path
                if self._load_single_skill(Path(meta.source)):
                    reloaded += 1
        return reloaded

    def _load_single_skill(self, filepath: Path) -> bool:
        """Load a single skill file. Returns True on success."""
        module = _load_module_from_path(filepath)
        if module is None:
            return False

        # Look for skill_meta
        meta = getattr(module, "skill_meta", None)
        if meta is None:
            # Try to auto-detect
            meta = self._auto_detect_meta(module, filepath)
            if meta is None:
                return False

        # Look for skill class
        skill_class = getattr(module, "SkillClass", None)
        instance = skill_class() if skill_class else None

        meta.source = str(filepath)
        self._registry.register(meta, instance)
        return True

    def _auto_detect_meta(self, module: Any, filepath: Path) -> SkillMeta | None:
        """Auto-detect skill metadata from module attributes."""
        name = getattr(module, "SKILL_NAME", filepath.stem)
        desc = getattr(module, "SKILL_DESCRIPTION", "")
        if not name:
            return None
        return SkillMeta(name=name, description=desc, source=str(filepath))
