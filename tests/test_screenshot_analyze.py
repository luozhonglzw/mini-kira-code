"""Tests for screenshot_analyze skill: preprocessing, API, registry."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kiracode.skills.loader import SkillLoader
from kiracode.skills.registry import SkillMeta, SkillRegistry

# ── Helpers ─────────────────────────────────────────────────────────────────

# Minimal valid 1x1 red PNG
_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
    b"\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00"
    b"\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)

_TINY_PNG_B64 = base64.b64encode(_TINY_PNG).decode("utf-8")


# ── Test: Image Input Parsing ───────────────────────────────────────────────


@pytest.mark.unit
class TestImageInputParsing:
    """Test _load_image_input with various input formats."""

    def test_base64_data_uri(self):
        from kiracode.skills.builtin.screenshot_analyze import _load_image_input

        data_uri = f"data:image/png;base64,{_TINY_PNG_B64}"
        img_bytes, mime = _load_image_input(data_uri)
        assert img_bytes == _TINY_PNG
        assert mime == "image/png"

    def test_raw_base64(self):
        from kiracode.skills.builtin.screenshot_analyze import _load_image_input

        img_bytes, mime = _load_image_input(_TINY_PNG_B64)
        assert img_bytes == _TINY_PNG
        assert mime == "image/png"

    def test_file_path(self, tmp_path):
        from kiracode.skills.builtin.screenshot_analyze import _load_image_input

        img_path = tmp_path / "test.png"
        img_path.write_bytes(_TINY_PNG)
        img_bytes, mime = _load_image_input(str(img_path))
        assert img_bytes == _TINY_PNG
        assert mime == "image/png"

    def test_file_not_found(self):
        from kiracode.skills.builtin.screenshot_analyze import _load_image_input

        with pytest.raises(FileNotFoundError):
            _load_image_input("/nonexistent/path.png")

    def test_invalid_data_uri(self):
        from kiracode.skills.builtin.screenshot_analyze import _load_image_input

        with pytest.raises(ValueError):
            _load_image_input("data:image/png;base64,!!!invalid!!!")


# ── Test: MD5 Cache ─────────────────────────────────────────────────────────


@pytest.mark.unit
class TestCache:
    def test_cache_hit(self):
        from kiracode.skills.builtin.screenshot_analyze import (
            _compute_image_md5,
            _get_cached_result,
            _set_cached_result,
            _result_cache,
        )

        # Clear cache
        _result_cache.clear()

        md5 = _compute_image_md5(_TINY_PNG)
        assert len(md5) == 32

        # Miss
        assert _get_cached_result(md5) is None

        # Set
        mock_result = {"components": [], "layout": {}}
        _set_cached_result(md5, mock_result)

        # Hit
        assert _get_cached_result(md5) == mock_result

    def test_cache_eviction(self):
        from kiracode.skills.builtin.screenshot_analyze import (
            _set_cached_result,
            _get_cached_result,
            _result_cache,
            _CACHE_MAX_SIZE,
        )

        _result_cache.clear()
        for i in range(_CACHE_MAX_SIZE + 5):
            _set_cached_result(f"key_{i}", {"idx": i})

        assert len(_result_cache) <= _CACHE_MAX_SIZE
        # First keys should be evicted
        assert _get_cached_result("key_0") is None


# ── Test: Qwen-VL Response Parsing ─────────────────────────────────────────


@pytest.mark.unit
class TestResponseParsing:
    def test_parse_json_response(self):
        from kiracode.skills.builtin.screenshot_analyze import _parse_vl_response

        raw = json.dumps({
            "components": [{"type": "button", "text": "Submit"}],
            "layout": {"type": "flex"},
        })
        result = _parse_vl_response(raw)
        assert result["components"][0]["type"] == "button"

    def test_parse_markdown_fenced(self):
        from kiracode.skills.builtin.screenshot_analyze import _parse_vl_response

        raw = '```json\n{"components": [], "layout": {}}\n```'
        result = _parse_vl_response(raw)
        assert "components" in result

    def test_parse_garbage_fallback(self):
        from kiracode.skills.builtin.screenshot_analyze import _parse_vl_response

        result = _parse_vl_response("This is not JSON at all")
        assert result.get("parse_error") is True
        assert result["components"] == []


# ── Test: OpenCV Preprocessing ──────────────────────────────────────────────


@pytest.mark.unit
class TestPreprocessing:
    def test_preprocess_returns_bytes(self):
        """Preprocessing should return valid JPEG bytes."""
        try:
            import cv2
            import numpy as np
        except ImportError:
            pytest.skip("OpenCV not installed")

        from kiracode.skills.builtin.screenshot_analyze import _preprocess_image

        # Create a small test image
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        img[:, :] = [255, 0, 0]  # red
        _, buf = cv2.imencode(".png", img)
        png_bytes = buf.tobytes()

        result = _preprocess_image(png_bytes, detail_level="fast")
        assert len(result) > 0
        # Verify it's valid JPEG
        assert result[:2] == b"\xff\xd8"

    def test_preprocess_resize_large_image(self):
        """Large images should be resized to fit within 1024px."""
        try:
            import cv2
            import numpy as np
        except ImportError:
            pytest.skip("OpenCV not installed")

        from kiracode.skills.builtin.screenshot_analyze import _preprocess_image

        # Create a large image
        img = np.zeros((2048, 2048, 3), dtype=np.uint8)
        _, buf = cv2.imencode(".png", img)
        png_bytes = buf.tobytes()

        result = _preprocess_image(png_bytes, detail_level="fast")
        # Decode result and check dimensions
        nparr = np.frombuffer(result, np.uint8)
        decoded = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        h, w = decoded.shape[:2]
        assert max(h, w) <= 1024


# ── Test: Skill Registry Integration ───────────────────────────────────────


@pytest.mark.unit
class TestRegistryIntegration:
    def test_auto_discovered_by_loader(self):
        """screenshot_analyze should be auto-loaded from builtin directory."""
        reg = SkillRegistry()
        loader = SkillLoader(reg)
        count = loader.load_from_directory("kiracode/skills/builtin")

        assert count >= 5  # 4 existing + screenshot_analyze
        skill = reg.get("screenshot_analyze")
        assert skill is not None
        assert "screenshot" in skill.tags
        assert "screenshot_analyze" in skill.capabilities

    def test_skill_instance_has_execute(self):
        """The loaded instance should have an async execute method."""
        reg = SkillRegistry()
        loader = SkillLoader(reg)
        loader.load_from_directory("kiracode/skills/builtin")

        instance = reg.get_instance("screenshot_analyze")
        assert instance is not None
        assert hasattr(instance, "execute")
        assert callable(instance.execute)

    def test_router_finds_screenshot_skill(self):
        """SkillRouter should route screenshot-related queries to this skill."""
        from kiracode.skills.router import SkillRouter

        reg = SkillRegistry()
        loader = SkillLoader(reg)
        loader.load_from_directory("kiracode/skills/builtin")
        router = SkillRouter(reg)

        queries = [
            "帮我分析这个截图",
            "实现这个界面",
            "screenshot analyze",
            "根据这个设计稿生成代码",
        ]
        for q in queries:
            results = router.route(q, top_k=3)
            skill_names = [r.skill_name for r in results]
            assert "screenshot_analyze" in skill_names, f"Query '{q}' did not route to screenshot_analyze, got {skill_names}"


# ── Test: SkillClass.execute (mocked API) ───────────────────────────────────


@pytest.mark.unit
class TestSkillClassExecute:
    @pytest.mark.asyncio
    async def test_execute_success(self, tmp_path):
        """Full execute flow with mocked Qwen-VL API."""
        from kiracode.skills.builtin.screenshot_analyze import SkillClass

        # Write test image
        img_path = tmp_path / "test.png"
        img_path.write_bytes(_TINY_PNG)

        mock_analysis = {
            "components": [
                {"type": "button", "text": "Click me", "position": {"x": 10, "y": 10, "width": 100, "height": 40}}
            ],
            "layout": {"type": "flex", "direction": "vertical"},
            "colors": {"primary": "#007bff"},
        }

        skill = SkillClass()
        skill._api_key = "test-key"

        with patch(
            "kiracode.skills.builtin.screenshot_analyze._call_qwen_vl",
            new_callable=AsyncMock,
            return_value=mock_analysis,
        ):
            result = await skill.execute(image_input=str(img_path), detail_level="standard")

        assert result["success"] is True
        assert result["components"][0]["type"] == "button"
        assert result["cached"] is False

    @pytest.mark.asyncio
    async def test_execute_cache_hit(self, tmp_path):
        """Second call with same image should return cached result."""
        from kiracode.skills.builtin.screenshot_analyze import SkillClass, _result_cache

        _result_cache.clear()
        img_path = tmp_path / "test.png"
        img_path.write_bytes(_TINY_PNG)

        mock_analysis = {"components": [], "layout": {}}

        skill = SkillClass()
        skill._api_key = "test-key"

        with patch(
            "kiracode.skills.builtin.screenshot_analyze._call_qwen_vl",
            new_callable=AsyncMock,
            return_value=mock_analysis,
        ):
            r1 = await skill.execute(image_input=str(img_path))
            r2 = await skill.execute(image_input=str(img_path))

        assert r1["cached"] is False
        assert r2["cached"] is True

    @pytest.mark.asyncio
    async def test_execute_no_api_key(self):
        """Should return error when API key is missing."""
        from kiracode.skills.builtin.screenshot_analyze import SkillClass

        skill = SkillClass()
        skill._api_key = ""

        result = await skill.execute(image_input="data:image/png;base64,abc")
        assert result["success"] is False
        assert "DASHSCOPE_API_KEY" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_file_not_found(self):
        """Should return error for missing file."""
        from kiracode.skills.builtin.screenshot_analyze import SkillClass

        skill = SkillClass()
        skill._api_key = "test-key"

        result = await skill.execute(image_input="/nonexistent/img.png")
        assert result["success"] is False
        assert "not found" in result["error"].lower()


# ── Test: YOLO UI Detector ─────────────────────────────────────────────────


@pytest.mark.unit
class TestUIDetector:
    def test_import_without_ultralytics(self):
        """UIDetector should be importable even without ultralytics."""
        from kiracode.models.ui_detector import UIDetector
        detector = UIDetector()
        assert detector._model is None

    def test_ui_classes_defined(self):
        from kiracode.models.ui_detector import UI_CLASSES
        assert "button" in UI_CLASSES
        assert "input" in UI_CLASSES
        assert len(UI_CLASSES) >= 10
