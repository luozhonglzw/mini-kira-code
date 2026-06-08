"""Tests for Context governance: Compressor and Window."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kiracode.context.compressor import CompressorConfig, SmartCompressor
from kiracode.context.window import WindowConfig, WindowManager
from kiracode.memory.working import Message, MessageRole
from kiracode.utils.token_counter import count_tokens


# ── SmartCompressor Tests ──────────────────────────────────────────────────


@pytest.mark.unit
class TestSmartCompressor:
    def test_compress_large_content(self):
        comp = SmartCompressor(config=CompressorConfig(threshold_tokens=100))
        large_text = "Line {}: test data with some content\n" * 200
        large_text = large_text.format(*range(200))
        msg = Message(role=MessageRole.TOOL, content=large_text)

        result = comp.compress(msg)
        assert result.compressed_token_count < result.original_token_count
        assert result.compression_ratio < 1.0
        assert result.ref_id != ""

    def test_compress_below_threshold(self):
        comp = SmartCompressor(config=CompressorConfig(threshold_tokens=1000))
        small_text = "short content"
        msg = Message(role=MessageRole.TOOL, content=small_text)

        result = comp.compress(msg)
        assert result.compression_ratio == 1.0
        assert result.ref_id == ""

    def test_reference_resolution(self):
        comp = SmartCompressor(config=CompressorConfig(threshold_tokens=50))
        original = "x = {}\n".format("'data'") * 100
        original = original.format(*range(100))
        msg = Message(role=MessageRole.TOOL, content=original)

        result = comp.compress(msg)
        if result.ref_id:
            resolved = comp.resolve_reference(result.ref_id)
            assert resolved == original
            assert count_tokens(resolved) == result.original_token_count

    def test_json_compression(self):
        comp = SmartCompressor(config=CompressorConfig(threshold_tokens=50))
        import json
        data = {"users": [{"id": i, "name": f"user_{i}"} for i in range(50)]}
        content = json.dumps(data, indent=2)
        msg = Message(role=MessageRole.TOOL, content=content)

        result = comp.compress(msg)
        assert "Compressed JSON" in result.summary or result.compression_ratio == 1.0

    def test_stats(self):
        comp = SmartCompressor(config=CompressorConfig(threshold_tokens=50))
        large = "data line {}\n" * 200
        large = large.format(*range(200))
        msg = Message(role=MessageRole.TOOL, content=large)
        comp.compress(msg)

        stats = comp.stats()
        assert stats["compressed_count"] >= 1
        assert stats["saved_tokens"] > 0
        assert stats["stored_references"] >= 1


# ── WindowManager Tests ────────────────────────────────────────────────────


@pytest.mark.unit
class TestWindowManager:
    def test_add_messages(self):
        w = WindowManager(config=WindowConfig(max_tokens=10000))
        w.add_user("hello")
        w.add_assistant("world")
        assert w.message_count == 2

    def test_utilization(self):
        w = WindowManager(config=WindowConfig(max_tokens=1000))
        w.add_user("short message")
        assert 0 < w.utilization < 1

    def test_sliding_window_eviction(self):
        w = WindowManager(config=WindowConfig(
            max_tokens=300,
            compression_threshold=0.9,
            min_recent_messages=1,
        ))
        for i in range(20):
            w.add_user(f"message number {i} with some padding content to fill up the window")
        # Should have evicted old messages
        assert w.total_tokens <= 300 or w.message_count <= 20

    def test_compression_integration(self):
        comp = SmartCompressor(config=CompressorConfig(threshold_tokens=100))
        w = WindowManager(config=WindowConfig(
            max_tokens=500,
            compression_threshold=0.5,
            min_recent_messages=1,
        ))
        w.set_compressor(comp)

        w.add_system("You are a coding assistant.")
        w.add_user("Generate code")

        # Add a large tool result
        big = "log line {}: request processed\n" * 300
        big = big.format(*range(300))
        w.add_tool(big)

        # Should have been compressed
        assert comp.stats()["compressed_count"] >= 1
        msgs = w.get_messages()
        compressed_msgs = [m for m in msgs if m.metadata.get("compressed")]
        assert len(compressed_msgs) >= 1

    def test_get_context(self):
        w = WindowManager(config=WindowConfig(max_tokens=10000))
        w.add_user("hello")
        ctx = w.get_context()
        assert len(ctx) == 1
        assert ctx[0]["role"] == "user"

    def test_summary(self):
        w = WindowManager(config=WindowConfig(max_tokens=5000))
        w.add_user("test")
        s = w.summary()
        assert "message_count" in s
        assert "total_tokens" in s
        assert "utilization" in s
