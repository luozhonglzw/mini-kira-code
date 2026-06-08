"""Tests for MimoProvider — MiMo (Anthropic-compatible) provider."""

from __future__ import annotations

import json
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock

from kiracode.llm.base import LLMMessage, MessageRole
from kiracode.llm.mimo_provider import MimoProvider


# ── Fixtures ────────────────────────────────────────────────────────────────


def _mock_anthropic_response(
    text: str = "Hello!",
    tool_use: list | None = None,
    stop_reason: str = "end_turn",
    usage: dict | None = None,
) -> dict:
    """Build a mock Anthropic Messages API response."""
    content_blocks = [{"type": "text", "text": text}]
    if tool_use:
        content_blocks.extend(tool_use)
    return {
        "id": "msg-mock",
        "model": "mimo-v2.5-pro",
        "type": "message",
        "role": "assistant",
        "content": content_blocks,
        "stop_reason": stop_reason,
        "usage": usage or {"input_tokens": 10, "output_tokens": 5},
    }


def _make_provider(**kwargs) -> MimoProvider:
    return MimoProvider(api_key="tp-test-key-xxxx", **kwargs)


# ── Tests ───────────────────────────────────────────────────────────────────


class TestMimoProviderInit:
    def test_default_init(self):
        p = MimoProvider(api_key="tp-test")
        assert p.model == "mimo-v2.5-pro"

    def test_custom_model(self):
        p = MimoProvider(api_key="tp-test", model="mimo-v2.5")
        assert p.model == "mimo-v2.5"

    def test_provider_name(self):
        p = MimoProvider(api_key="tp-test")
        assert p.provider_name == "mimo"

    def test_no_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
        monkeypatch.delenv("MIMO_API_KEY", raising=False)
        with pytest.raises(ValueError, match="API key required"):
            MimoProvider(api_key="")


class TestMimoProviderMessageFormat:
    def test_basic_user_message(self):
        p = _make_provider()
        msgs = [LLMMessage(role=MessageRole.USER, content="Hi")]
        system, formatted = p._format_messages(msgs)
        assert system == ""
        assert formatted == [{"role": "user", "content": "Hi"}]

    def test_system_message_extracted(self):
        p = _make_provider()
        msgs = [
            LLMMessage(role=MessageRole.SYSTEM, content="You are helpful"),
            LLMMessage(role=MessageRole.USER, content="Hi"),
        ]
        system, formatted = p._format_messages(msgs)
        assert system == "You are helpful"
        assert len(formatted) == 1
        assert formatted[0]["role"] == "user"

    def test_assistant_message(self):
        p = _make_provider()
        msgs = [LLMMessage(role=MessageRole.ASSISTANT, content="Hello!")]
        _, formatted = p._format_messages(msgs)
        assert formatted[0]["role"] == "assistant"
        assert formatted[0]["content"] == [{"type": "text", "text": "Hello!"}]

    def test_tool_result_message(self):
        p = _make_provider()
        msgs = [LLMMessage(role=MessageRole.TOOL, content='{"ok": true}', tool_call_id="call_123")]
        _, formatted = p._format_messages(msgs)
        assert formatted[0]["role"] == "user"
        assert formatted[0]["content"][0]["type"] == "tool_result"
        assert formatted[0]["content"][0]["tool_use_id"] == "call_123"

    def test_assistant_with_tool_calls(self):
        p = _make_provider()
        msgs = [LLMMessage(
            role=MessageRole.ASSISTANT,
            content="I'll help",
            metadata={"tool_calls": [
                {"id": "call_1", "function": {"name": "write_file", "arguments": '{"path":"a.txt","content":"hi"}'}}
            ]},
        )]
        _, formatted = p._format_messages(msgs)
        blocks = formatted[0]["content"]
        assert len(blocks) == 2
        assert blocks[0]["type"] == "text"
        assert blocks[1]["type"] == "tool_use"
        assert blocks[1]["name"] == "write_file"


class TestMimoProviderToolConversion:
    def test_convert_openai_tools_to_anthropic(self):
        p = _make_provider()
        openai_tools = [{
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "Write a file",
                "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
            },
        }]
        result = p._convert_tools(openai_tools)
        assert result is not None
        assert len(result) == 1
        assert result[0]["name"] == "write_file"
        assert result[0]["description"] == "Write a file"
        assert "properties" in result[0]["input_schema"]

    def test_convert_none_returns_none(self):
        p = _make_provider()
        assert p._convert_tools(None) is None


class TestMimoProviderChat:
    @pytest.mark.asyncio
    async def test_chat_simple_response(self):
        p = _make_provider()
        mock_resp_data = _mock_anthropic_response(text="Hi there!")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_resp_data
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.is_closed = False
        p._client = mock_client

        msgs = [LLMMessage(role=MessageRole.USER, content="Hello")]
        result = await p.chat(msgs)

        assert result.content == "Hi there!"
        assert result.provider == "mimo"
        assert result.model == "mimo-v2.5-pro"
        assert result.finish_reason == "stop"
        assert result.usage["prompt_tokens"] == 10
        assert result.usage["completion_tokens"] == 5

        # Verify request went to /v1/messages
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "/v1/messages"

    @pytest.mark.asyncio
    async def test_chat_with_tools(self):
        p = _make_provider()
        tool_block = {
            "type": "tool_use",
            "id": "call_abc",
            "name": "write_file",
            "input": {"path": "test.txt", "content": "hello"},
        }
        mock_resp_data = _mock_anthropic_response(
            text="I'll write that file",
            tool_use=[tool_block],
            stop_reason="tool_use",
        )

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_resp_data
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.is_closed = False
        p._client = mock_client

        tools = [{"type": "function", "function": {"name": "write_file", "description": "Write", "parameters": {}}}]
        msgs = [LLMMessage(role=MessageRole.USER, content="Write test.txt")]
        result = await p.chat(msgs, tools=tools)

        assert result.content == "I'll write that file"
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["function"]["name"] == "write_file"
        assert result.finish_reason == "tool_calls"

    @pytest.mark.asyncio
    async def test_chat_400_raises_valueerror(self):
        p = _make_provider()

        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "Bad request"
        mock_resp.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError("400", request=MagicMock(), response=mock_resp)
        )

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.is_closed = False
        p._client = mock_client

        with pytest.raises(ValueError, match="400"):
            await p.chat([LLMMessage(role=MessageRole.USER, content="Hi")])

    @pytest.mark.asyncio
    async def test_chat_429_raises_runtimeerror(self):
        p = _make_provider()

        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = "Rate limited"
        mock_resp.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError("429", request=MagicMock(), response=mock_resp)
        )

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.is_closed = False
        p._client = mock_client

        with pytest.raises(RuntimeError, match="429"):
            await p.chat([LLMMessage(role=MessageRole.USER, content="Hi")])

    @pytest.mark.asyncio
    async def test_chat_502_raises_connectionerror(self):
        p = _make_provider()

        mock_resp = MagicMock()
        mock_resp.status_code = 502
        mock_resp.text = "Bad Gateway"
        mock_resp.raise_for_status = MagicMock(
            side_effect=httpx.HTTPStatusError("502", request=MagicMock(), response=mock_resp)
        )

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.is_closed = False
        p._client = mock_client

        with pytest.raises(ConnectionError, match="502"):
            await p.chat([LLMMessage(role=MessageRole.USER, content="Hi")])


class TestMimoProviderMultiTurn:
    @pytest.mark.asyncio
    async def test_tool_result_roundtrip(self):
        """Simulate: user → assistant with tool_use → tool_result → final answer."""
        p = _make_provider()

        # Step 1: LLM returns tool_use
        tool_block = {
            "type": "tool_use",
            "id": "call_1",
            "name": "read_file",
            "input": {"path": "test.txt"},
        }
        resp1_data = _mock_anthropic_response(text="Let me read that", tool_use=[tool_block], stop_reason="tool_use")

        mock_resp1 = MagicMock()
        mock_resp1.status_code = 200
        mock_resp1.json.return_value = resp1_data
        mock_resp1.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp1)
        mock_client.is_closed = False
        p._client = mock_client

        msgs = [LLMMessage(role=MessageRole.USER, content="Read test.txt")]
        resp1 = await p.chat(msgs)
        assert len(resp1.tool_calls) == 1

        # Step 2: Feed back tool result
        msgs.append(LLMMessage(
            role=MessageRole.ASSISTANT,
            content=resp1.content,
            metadata={"tool_calls": resp1.tool_calls},
        ))
        msgs.append(LLMMessage(role=MessageRole.TOOL, content="file contents here", tool_call_id="call_1"))

        resp2_data = _mock_anthropic_response(text="The file contains: file contents here")
        mock_resp2 = MagicMock()
        mock_resp2.status_code = 200
        mock_resp2.json.return_value = resp2_data
        mock_resp2.raise_for_status = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_resp2)

        resp2 = await p.chat(msgs)
        assert resp2.content == "The file contains: file contents here"

        # Verify the second request included tool_result in messages
        call_args = mock_client.post.call_args
        payload = call_args[1]["json"] if "json" in call_args[1] else call_args[0][1]
        # Should have: user, assistant (with tool_use), user (with tool_result)
        assert len(payload["messages"]) == 3
        tool_result_msg = payload["messages"][2]
        assert tool_result_msg["role"] == "user"
        assert tool_result_msg["content"][0]["type"] == "tool_result"


class TestMimoProviderFactory:
    def test_factory_create_mimo(self):
        from kiracode.llm.factory import create_provider
        p = create_provider("mimo", model="mimo-v2.5-pro", api_key="tp-test")
        assert isinstance(p, MimoProvider)
        assert p.model == "mimo-v2.5-pro"

    def test_factory_mimo_default_model(self):
        from kiracode.llm.factory import create_provider
        p = create_provider("mimo", api_key="tp-test")
        assert p.model == "mimo-v2.5-pro"
