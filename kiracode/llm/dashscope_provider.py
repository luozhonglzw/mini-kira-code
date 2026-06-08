"""DashScope LLM Provider — Alibaba Cloud 百炼 (OpenAI-compatible).

Design decisions:
- Uses httpx for async HTTP (same pattern as MiMoProvider).
- DashScope's compatible-mode endpoint mirrors OpenAI's /chat/completions.
- API key from DASHSCOPE_API_KEY env var.
- Supports tool_calls in OpenAI function-calling format.
- Default model: qwen-max (best quality) / qwen-plus (faster/cheaper).

Usage:
    provider = DashScopeProvider(api_key="sk-xxx")
    response = await provider.chat([LLMMessage(role="user", content="Hello")])
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, AsyncIterator

import httpx

from kiracode.llm.base import LLMMessage, LLMProvider, LLMResponse, MessageRole

logger = logging.getLogger(__name__)


class DashScopeProvider(LLMProvider):
    """Alibaba Cloud DashScope (百炼) provider — OpenAI-compatible."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "qwen-max",
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
        timeout: int = 300,
        **kwargs: Any,
    ) -> None:
        super().__init__(model, **kwargs)
        self._api_key = api_key or os.environ.get("DASHSCOPE_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "DashScope API key required. "
                "Set DASHSCOPE_API_KEY env var or pass api_key= parameter."
            )
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(connect=60.0, read=float(self._timeout), write=float(self._timeout), pool=float(self._timeout)),
            )
        return self._client

    def _format_messages(self, messages: list[LLMMessage]) -> list[dict[str, Any]]:
        """Convert LLMMessage list to OpenAI format."""
        formatted: list[dict[str, Any]] = []
        for msg in messages:
            entry: dict[str, Any] = {"role": msg.role.value, "content": msg.content}
            if msg.name:
                entry["name"] = msg.name
            if msg.tool_call_id:
                entry["tool_call_id"] = msg.tool_call_id
            # Preserve tool_calls in assistant messages (for multi-turn tool use)
            if msg.role == MessageRole.ASSISTANT and msg.metadata.get("tool_calls"):
                entry["tool_calls"] = msg.metadata["tool_calls"]
            formatted.append(entry)
        return formatted

    async def chat(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        client = await self._get_client()
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": self._format_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = tools
        payload.update(kwargs)

        logger.info(
            "DashScope request: model=%s, messages=%d, tools=%d",
            self._model,
            len(messages),
            len(tools) if tools else 0,
        )

        try:
            resp = await client.post("/chat/completions", json=payload)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            body = e.response.text
            if status == 400:
                raise ValueError(f"DashScope 400 Bad Request: {body}") from e
            elif status == 401:
                raise ValueError(f"DashScope 401 Unauthorized: check DASHSCOPE_API_KEY") from e
            elif status == 429:
                raise RuntimeError(f"DashScope 429 Rate Limited: {body}") from e
            elif status >= 500:
                raise ConnectionError(f"DashScope {status} Server Error: {body}") from e
            raise
        except json.JSONDecodeError as e:
            raise ValueError(f"DashScope returned invalid JSON: {e}") from e

        data = resp.json()
        choice = data["choices"][0]
        message = choice["message"]
        usage = data.get("usage", {})

        # Parse tool_calls if present
        tool_calls = message.get("tool_calls") or []
        parsed_tool_calls = []
        for tc in tool_calls:
            func = tc.get("function", {})
            parsed_tool_calls.append({
                "id": tc.get("id", ""),
                "type": "function",
                "function": {
                    "name": func.get("name", ""),
                    "arguments": func.get("arguments", "{}"),
                },
            })

        return LLMResponse(
            content=message.get("content") or "",
            model=data.get("model", self._model),
            provider="dashscope",
            usage={
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
            finish_reason=choice.get("finish_reason", "stop"),
            tool_calls=parsed_tool_calls,
        )

    async def stream(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        client = await self._get_client()
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": self._format_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        payload.update(kwargs)

        try:
            async with client.stream("POST", "/chat/completions", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: ") and line != "data: [DONE]":
                        chunk = json.loads(line[6:])
                        delta = chunk["choices"][0].get("delta", {})
                        if "content" in delta:
                            yield delta["content"]
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 429:
                raise RuntimeError("DashScope 429 Rate Limited") from e
            elif status >= 500:
                raise ConnectionError(f"DashScope {status} Server Error") from e
            raise

    async def count_tokens(self, messages: list[LLMMessage]) -> int:
        try:
            import tiktoken
            encoding = tiktoken.get_encoding("cl100k_base")
            total = 0
            for msg in messages:
                total += 4
                total += len(encoding.encode(msg.content))
            return total + 2
        except ImportError:
            return sum(len(m.content) // 4 + 1 for m in messages)

    async def health_check(self) -> bool:
        try:
            client = await self._get_client()
            resp = await client.get("/models")
            return resp.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        """Close the httpx client. Call this when done with the provider."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
