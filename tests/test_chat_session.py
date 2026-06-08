"""Tests for ChatSession — interactive multi-turn chat REPL."""

from __future__ import annotations

import asyncio
import pytest
import re
from unittest.mock import AsyncMock, MagicMock, patch

from kiracode.cli.chat import ChatSession
from kiracode.llm.base import LLMMessage, MessageRole


# ── Fixtures ────────────────────────────────────────────────────────────────


def _make_session(**kwargs) -> ChatSession:
    return ChatSession(provider_name="mock", model="mock-model", max_budget=50000, **kwargs)


# ── Tests ───────────────────────────────────────────────────────────────────


class TestChatSessionInit:
    def test_default_init(self):
        s = _make_session()
        assert s.provider.provider_name == "mock"
        assert s.provider.model == "mock-model"
        assert s.budget.total == 50000
        assert len(s.messages) == 0
        assert s.round_count == 0

    def test_session_id_is_unique(self):
        s1 = _make_session()
        s2 = _make_session()
        assert s1.session_id != s2.session_id

    def test_memory_initialized(self):
        s = _make_session()
        assert s.memory is not None
        assert s.memory.working is not None
        assert s.memory.episodic is not None
        assert s.memory.semantic is not None


class TestChatSessionMessageBuild:
    def test_build_messages_includes_system(self):
        s = _make_session()
        messages = s._build_messages("")
        assert len(messages) == 1
        assert messages[0].role == MessageRole.SYSTEM

    def test_build_messages_with_memory(self):
        s = _make_session()
        messages = s._build_messages("some recalled memory")
        assert "some recalled memory" in messages[0].content

    def test_build_messages_includes_history(self):
        s = _make_session()
        s.messages.append(LLMMessage(role=MessageRole.USER, content="Hi"))
        s.messages.append(LLMMessage(role=MessageRole.ASSISTANT, content="Hello"))
        messages = s._build_messages("")
        assert len(messages) == 3  # system + 2 history
        assert messages[1].content == "Hi"
        assert messages[2].content == "Hello"

    def test_build_messages_preserves_reasoning_content(self):
        s = _make_session()
        s.messages.append(LLMMessage(
            role=MessageRole.ASSISTANT,
            content="Answer",
            reasoning_content="Step by step thinking...",
        ))
        messages = s._build_messages("")
        assert messages[1].reasoning_content == "Step by step thinking..."


class TestChatSessionChatTurn:
    @pytest.mark.asyncio
    async def test_single_turn(self):
        s = _make_session()
        await s._chat_turn("Hello")
        assert s.round_count == 1
        assert len(s.messages) == 2  # user + assistant
        assert s.messages[0].role == MessageRole.USER
        assert s.messages[1].role == MessageRole.ASSISTANT

    @pytest.mark.asyncio
    async def test_multi_turn_history_grows(self):
        s = _make_session()
        await s._chat_turn("First")
        await s._chat_turn("Second")
        assert s.round_count == 2
        assert len(s.messages) == 4  # 2 user + 2 assistant

    @pytest.mark.asyncio
    async def test_token_tracking(self):
        s = _make_session()
        await s._chat_turn("Test")
        assert s.total_prompt_tokens > 0
        assert s.total_completion_tokens > 0


class TestChatSessionCommands:
    def test_cmd_clear(self):
        s = _make_session()
        s.messages.append(LLMMessage(role=MessageRole.USER, content="test"))
        s.round_count = 5
        s._cmd_clear()
        assert len(s.messages) == 0
        assert s.round_count == 0

    def test_cmd_consolidate(self):
        s = _make_session()
        # Should not raise
        s._cmd_consolidate()

    def test_cmd_save(self, tmp_path):
        s = _make_session()
        s.messages.append(LLMMessage(role=MessageRole.USER, content="test query"))
        s.messages.append(LLMMessage(role=MessageRole.ASSISTANT, content="test response"))
        s.round_count = 1

        filepath = tmp_path / "session.md"
        s._cmd_save(str(filepath))
        assert filepath.exists()
        content = filepath.read_text(encoding="utf-8")
        assert "test query" in content
        assert "test response" in content
        assert "Round 1" in content

    def test_handle_command_quit(self):
        s = _make_session()
        assert s._handle_command("/quit") is True
        assert s._handle_command("/q") is True

    def test_handle_command_unknown(self):
        s = _make_session()
        assert s._handle_command("/unknown") is False

    def test_cmd_memory(self):
        s = _make_session()
        # Should not raise
        s._cmd_memory()

    def test_cmd_budget(self):
        s = _make_session()
        # Should not raise
        s._cmd_budget()

    def test_cmd_audit(self):
        s = _make_session()
        # Should not raise
        s._cmd_audit()

    @pytest.mark.asyncio
    async def test_cmd_security_no_code(self):
        s = _make_session()
        # No code blocks → should print "no code blocks" message
        await s._cmd_security()

    @pytest.mark.asyncio
    async def test_cmd_security_with_code(self):
        s = _make_session()
        s.messages.append(LLMMessage(
            role=MessageRole.ASSISTANT,
            content='Here is code:\n```python\nimport os\nos.system("ls")\n```',
        ))
        await s._cmd_security()
