"""Tests for Skill system: Registry, Loader, Router."""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kiracode.skills.loader import SkillLoader
from kiracode.skills.registry import SkillMeta, SkillRegistry
from kiracode.skills.router import SkillRouter


# ── SkillRegistry Tests ────────────────────────────────────────────────────


@pytest.mark.unit
class TestSkillRegistry:
    def test_register_and_get(self):
        reg = SkillRegistry()
        meta = SkillMeta(name="test_skill", description="A test skill", tags=["test"])
        reg.register(meta)

        found = reg.get("test_skill")
        assert found is not None
        assert found.name == "test_skill"
        assert reg.get("nonexistent") is None

    def test_register_with_instance(self):
        reg = SkillRegistry()
        meta = SkillMeta(name="my_skill", description="test")
        instance = {"type": "mock"}
        reg.register(meta, instance)

        assert reg.get_instance("my_skill") == instance

    def test_unregister(self):
        reg = SkillRegistry()
        reg.register(SkillMeta(name="temp", description="temp"))
        assert reg.unregister("temp") is True
        assert reg.get("temp") is None
        assert reg.unregister("temp") is False

    def test_list_skills(self):
        reg = SkillRegistry()
        reg.register(SkillMeta(name="a", description="a", enabled=True))
        reg.register(SkillMeta(name="b", description="b", enabled=False))

        assert len(reg.list_skills(enabled_only=True)) == 1
        assert len(reg.list_skills(enabled_only=False)) == 2

    def test_search(self):
        reg = SkillRegistry()
        reg.register(SkillMeta(name="file_ops", description="Read and write files", tags=["file", "io"]))
        reg.register(SkillMeta(name="git_ops", description="Git operations", tags=["git"]))

        results = reg.search("file")
        assert len(results) == 1
        assert results[0].name == "file_ops"

    def test_summary(self):
        reg = SkillRegistry()
        reg.register(SkillMeta(name="a", description="a"))
        reg.register(SkillMeta(name="b", description="b"))
        s = reg.summary()
        assert s["total"] == 2
        assert s["enabled"] == 2
        assert set(s["names"]) == {"a", "b"}


# ── SkillLoader Tests ──────────────────────────────────────────────────────


@pytest.mark.unit
class TestSkillLoader:
    def test_load_builtin_skills(self):
        reg = SkillRegistry()
        loader = SkillLoader(reg)
        count = loader.load_from_directory("kiracode/skills/builtin")
        assert count == 5
        names = {s.name for s in reg.list_skills()}
        assert "file_ops" in names
        assert "shell_exec" in names
        assert "code_search" in names
        assert "git_ops" in names
        assert "screenshot_analyze" in names

    def test_load_nonexistent_directory(self):
        reg = SkillRegistry()
        loader = SkillLoader(reg)
        count = loader.load_from_directory("/nonexistent/path")
        assert count == 0


# ── SkillRouter Tests ──────────────────────────────────────────────────────


@pytest.mark.unit
class TestSkillRouter:
    def _setup_registry(self) -> SkillRegistry:
        reg = SkillRegistry()
        loader = SkillLoader(reg)
        loader.load_from_directory("kiracode/skills/builtin")
        return reg

    def test_route_file_query(self):
        reg = self._setup_registry()
        router = SkillRouter(reg)
        results = router.route("read the config file")
        assert len(results) > 0
        assert results[0].skill_name == "file_ops"

    def test_route_git_query(self):
        reg = self._setup_registry()
        router = SkillRouter(reg)
        results = router.route("check git status")
        assert len(results) > 0
        assert results[0].skill_name == "git_ops"

    def test_route_search_query(self):
        reg = self._setup_registry()
        router = SkillRouter(reg)
        results = router.route("search for login function in code")
        assert len(results) > 0
        assert results[0].skill_name == "code_search"

    def test_route_shell_query(self):
        reg = self._setup_registry()
        router = SkillRouter(reg)
        results = router.route("run pytest tests")
        assert len(results) > 0
        assert results[0].skill_name == "shell_exec"

    def test_route_returns_top_k(self):
        reg = self._setup_registry()
        router = SkillRouter(reg)
        results = router.route("file operations", top_k=2)
        assert len(results) <= 2

    def test_find_by_capability(self):
        reg = self._setup_registry()
        router = SkillRouter(reg)
        skills = router.find_by_capability("file_read")
        assert len(skills) >= 1
        assert skills[0].name == "file_ops"
