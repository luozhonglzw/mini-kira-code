"""MimoProvider — Xiaomi MiMo (Anthropic-compatible) provider.

Endpoint: https://token-plan-cn.xiaomimimo.com/anthropic
Uses Anthropic Messages API format (/v1/messages).
Auth: x-api-key header with tp-xxx token.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, AsyncIterator

import httpx

from kiracode.llm.base import LLMMessage, LLMProvider, LLMResponse, MessageRole

logger = logging.getLogger(__name__)

ANTHROPIC_VERSION = "2023-06-01"


class MimoProvider(LLMProvider):
    """Xiaomi MiMo provider — Anthropic Messages API compatible."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "mimo-v2.5-pro",
        base_url: str = "https://token-plan-cn.xiaomimimo.com/anthropic",
        timeout: int = 300,
        **kwargs: Any,
    ) -> None:
        super().__init__(model, **kwargs)
        self._api_key = api_key or os.environ.get("ANTHROPIC_AUTH_TOKEN", "") or os.environ.get("MIMO_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "MiMo API key required. "
                "Set ANTHROPIC_AUTH_TOKEN env var or pass api_key= parameter."
            )
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": ANTHROPIC_VERSION,
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(connect=60.0, read=float(self._timeout), write=float(self._timeout), pool=float(self._timeout)),
            )
        return self._client

    def _format_messages(self, messages: list[LLMMessage]) -> tuple[str, list[dict[str, Any]]]:
        """Convert LLMMessage list to Anthropic Messages format.

        Returns (system_prompt, messages_list).
        """
        system = ""
        formatted: list[dict[str, Any]] = []

        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                system = msg.content
                continue

            if msg.role == MessageRole.USER:
                formatted.append({"role": "user", "content": msg.content})

            elif msg.role == MessageRole.ASSISTANT:
                content_blocks: list[dict[str, Any]] = []
                if msg.content:
                    content_blocks.append({"type": "text", "text": msg.content})
                tool_calls = msg.metadata.get("tool_calls", [])
                for tc in tool_calls:
                    func = tc.get("function", {})
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": func.get("name", ""),
                        "input": json.loads(func.get("arguments", "{}")) if isinstance(func.get("arguments"), str) else func.get("arguments", {}),
                    })
                if content_blocks:
                    formatted.append({"role": "assistant", "content": content_blocks})
                else:
                    formatted.append({"role": "assistant", "content": msg.content or "(empty)"})

            elif msg.role == MessageRole.TOOL:
                formatted.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id,
                        "content": msg.content,
                    }],
                })

        return system, formatted

    def _convert_tools(self, tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
        """Convert OpenAI-style tools to Anthropic format."""
        if not tools:
            return None
        anthropic_tools = []
        for t in tools:
            func = t.get("function", {})
            anthropic_tools.append({
                "name": func.get("name", ""),
                "description": func.get("description", ""),
                "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
            })
        return anthropic_tools

    async def chat(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        client = await self._get_client()
        system, formatted = self._format_messages(messages)

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": formatted,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system:
            payload["system"] = system
        anthropic_tools = self._convert_tools(tools)
        if anthropic_tools:
            payload["tools"] = anthropic_tools
        payload.update(kwargs)

        logger.info(
            "MiMo request: model=%s, messages=%d, tools=%d",
            self._model, len(formatted), len(anthropic_tools) if anthropic_tools else 0,
        )

        try:
            resp = await client.post("/v1/messages", json=payload)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            body = e.response.text
            if status == 400:
                raise ValueError(f"MiMo 400 Bad Request: {body}") from e
            elif status == 401:
                raise ValueError(f"MiMo 401 Unauthorized: check API key") from e
            elif status == 429:
                raise RuntimeError(f"MiMo 429 Rate Limited: {body}") from e
            elif status >= 500:
                raise ConnectionError(f"MiMo {status} Server Error: {body}") from e
            raise

        data = resp.json()

        # Parse Anthropic response
        content_blocks = data.get("content", [])
        stop_reason = data.get("stop_reason", "end_turn")

        text_parts = []
        thinking_parts = []
        tool_calls = []
        for block in content_blocks:
            btype = block.get("type", "")
            if btype == "text":
                text_parts.append(block["text"])
            elif btype == "thinking":
                thinking_parts.append(block.get("thinking", ""))
            elif btype == "tool_use":
                tool_calls.append({
                    "id": block.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": block.get("name", ""),
                        "arguments": json.dumps(block.get("input", {}), ensure_ascii=False),
                    },
                })

        # Map Anthropic stop_reason to OpenAI finish_reason
        finish_map = {
            "end_turn": "stop",
            "max_tokens": "length",
            "tool_use": "tool_calls",
            "stop_sequence": "stop",
        }
        finish_reason = finish_map.get(stop_reason, "stop")

        usage = data.get("usage", {})
        return LLMResponse(
            content="".join(text_parts),
            model=data.get("model", self._model),
            provider="mimo",
            usage={
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            },
            finish_reason=finish_reason,
            tool_calls=tool_calls,
            reasoning_content="\n".join(thinking_parts) if thinking_parts else None,
        )

    async def stream(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        client = await self._get_client()
        system, formatted = self._format_messages(messages)

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": formatted,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        if system:
            payload["system"] = system

        try:
            async with client.stream("POST", "/v1/messages", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            event = json.loads(line[6:])
                            if event.get("type") == "content_block_delta":
                                delta = event.get("delta", {})
                                if delta.get("type") == "text_delta":
                                    yield delta.get("text", "")
                        except json.JSONDecodeError:
                            pass
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 429:
                raise RuntimeError("MiMo 429 Rate Limited") from e
            elif status >= 500:
                raise ConnectionError(f"MiMo {status} Server Error") from e
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
            resp = await client.get("/v1/models")
            return resp.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        """Close the httpx client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
