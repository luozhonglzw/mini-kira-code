"""Tests for DashScopeProvider — Alibaba Cloud 百炼 integration."""

from __future__ import annotations

import json
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from kiracode.llm.base import LLMMessage, MessageRole
from kiracode.llm.dashscope_provider import DashScopeProvider


# ── Fixtures ────────────────────────────────────────────────────────────────


def _mock_chat_response(
    content: str = "Hello!",
    tool_calls: list | None = None,
    usage: dict | None = None,
) -> dict:
    """Build a mock DashScope API response."""
    message: dict = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {
        "id": "chatcmpl-mock",
        "model": "qwen-max",
        "choices": [
            {"index": 0, "message": message, "finish_reason": "stop"}
        ],
        "usage": usage or {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def _make_provider(**kwargs) -> DashScopeProvider:
    return DashScopeProvider(api_key="sk-test-key-xxxx", **kwargs)


def _mock_httpx_response(json_data: dict, status_code: int = 200) -> MagicMock:
    """Build a mock httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = json.dumps(json_data)
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


# ── Tests ───────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestDashScopeProviderInit:
    def test_default_init(self):
        p = DashScopeProvider(api_key="sk-test")
        assert p.model == "qwen-max"
        assert p._base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"

    def test_custom_model(self):
        p = DashScopeProvider(api_key="sk-test", model="qwen-plus")
        assert p.model == "qwen-plus"

    def test_env_var_fallback(self, monkeypatch):
        monkeypatch.setenv("DASHSCOPE_API_KEY", "sk-from-env")
        p = DashScopeProvider()
        assert p._api_key == "sk-from-env"

    def test_provider_name(self):
        p = DashScopeProvider(api_key="sk-test")
        assert p.provider_name == "dashscope"


@pytest.mark.unit
class TestDashScopeFormatMessages:
    def test_basic_messages(self):
        p = _make_provider()
        msgs = [
            LLMMessage(role=MessageRole.SYSTEM, content="You are helpful."),
            LLMMessage(role=MessageRole.USER, content="Hello"),
        ]
        formatted = p._format_messages(msgs)
        assert len(formatted) == 2
        assert formatted[0] == {"role": "system", "content": "You are helpful."}
        assert formatted[1] == {"role": "user", "content": "Hello"}

    def test_tool_call_id_preserved(self):
        p = _make_provider()
        msg = LLMMessage(
            role=MessageRole.TOOL,
            content='{"result": "ok"}',
            tool_call_id="call_123",
        )
        formatted = p._format_messages([msg])
        assert formatted[0]["tool_call_id"] == "call_123"

    def test_assistant_tool_calls_in_metadata(self):
        p = _make_provider()
        tc = [{"id": "c1", "type": "function", "function": {"name": "foo", "arguments": "{}"}}]
        msg = LLMMessage(
            role=MessageRole.ASSISTANT,
            content="",
            metadata={"tool_calls": tc},
        )
        formatted = p._format_messages([msg])
        assert formatted[0]["tool_calls"] == tc


@pytest.mark.unit
class TestDashScopeChat:
    @pytest.mark.asyncio
    async def test_chat_success(self):
        p = _make_provider()
        api_resp = _mock_chat_response(content="def bubble_sort(arr): ...")

        with patch.object(p, "_get_client") as mock_get_client:
            client = AsyncMock()
            client.post = AsyncMock(return_value=_mock_httpx_response(api_resp))
            mock_get_client.return_value = client

            msgs = [LLMMessage(role=MessageRole.USER, content="写一个冒泡排序")]
            result = await p.chat(msgs)

            assert result.content == "def bubble_sort(arr): ..."
            assert result.provider == "dashscope"
            assert result.model == "qwen-max"
            assert result.usage["prompt_tokens"] == 10
            assert result.finish_reason == "stop"

    @pytest.mark.asyncio
    async def test_chat_with_tools(self):
        p = _make_provider()
        tool_calls = [{
            "id": "call_abc",
            "type": "function",
            "function": {"name": "write_file", "arguments": '{"path":"a.py","content":"x=1"}'},
        }]
        api_resp = _mock_chat_response(content="", tool_calls=tool_calls)

        with patch.object(p, "_get_client") as mock_get_client:
            client = AsyncMock()
            client.post = AsyncMock(return_value=_mock_httpx_response(api_resp))
            mock_get_client.return_value = client

            tools = [{"type": "function", "function": {"name": "write_file", "parameters": {}}}]
            msgs = [LLMMessage(role=MessageRole.USER, content="写一个冒泡排序")]
            result = await p.chat(msgs, tools=tools)

            assert len(result.tool_calls) == 1
            assert result.tool_calls[0]["function"]["name"] == "write_file"
            assert "call_abc" in result.tool_calls[0]["id"]

    @pytest.mark.asyncio
    async def test_chat_401_raises(self):
        p = _make_provider()
        mock_resp = _mock_httpx_response({"error": "unauthorized"}, status_code=401)

        with patch.object(p, "_get_client") as mock_get_client:
            client = AsyncMock()
            client.post = AsyncMock(return_value=mock_resp)
            mock_get_client.return_value = client

            with pytest.raises(ValueError, match="401"):
                await p.chat([LLMMessage(role=MessageRole.USER, content="hi")])

    @pytest.mark.asyncio
    async def test_chat_429_raises(self):
        p = _make_provider()
        mock_resp = _mock_httpx_response({"error": "rate limited"}, status_code=429)

        with patch.object(p, "_get_client") as mock_get_client:
            client = AsyncMock()
            client.post = AsyncMock(return_value=mock_resp)
            mock_get_client.return_value = client

            with pytest.raises(RuntimeError, match="429"):
                await p.chat([LLMMessage(role=MessageRole.USER, content="hi")])


@pytest.mark.unit
class TestDashScopeFactory:
    def test_factory_create_dashscope(self):
        from kiracode.llm.factory import create_provider
        p = create_provider("dashscope", model="qwen-plus", api_key="sk-test")
        assert isinstance(p, DashScopeProvider)
        assert p.model == "qwen-plus"

    def test_factory_dashscope_default_model(self):
        from kiracode.llm.factory import create_provider
        p = create_provider("dashscope", api_key="sk-test")
        assert p.model == "qwen-max"
