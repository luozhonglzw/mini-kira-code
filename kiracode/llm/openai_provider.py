"""OpenAI LLM Provider — implements LLMProvider for OpenAI-compatible APIs.

Design decisions:
- Uses httpx for async HTTP (not openai SDK) to minimize dependencies.
- Supports OpenAI, Azure OpenAI, and compatible endpoints (vLLM, Ollama).
- API key read from environment: OPENAI_API_KEY.
- Token counting uses tiktoken when available, falls back to heuristic.

Usage:
    provider = OpenAIProvider(model="gpt-4o", api_key="sk-...")
    response = await provider.chat([LLMMessage(role="user", content="Hello")])
"""

from __future__ import annotations

import os
from typing import Any, AsyncIterator

import httpx

from kiracode.llm.base import LLMMessage, LLMProvider, LLMResponse


class OpenAIProvider(LLMProvider):
    """OpenAI-compatible API provider."""

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        base_url: str = "https://api.openai.com/v1",
        **kwargs: Any,
    ) -> None:
        super().__init__(model, **kwargs)
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(60.0),
            )
        return self._client

    def _format_messages(self, messages: list[LLMMessage]) -> list[dict[str, Any]]:
        formatted = []
        for msg in messages:
            entry: dict[str, Any] = {"role": msg.role.value, "content": msg.content}
            if msg.name:
                entry["name"] = msg.name
            if msg.tool_call_id:
                entry["tool_call_id"] = msg.tool_call_id
            formatted.append(entry)
        return formatted

    async def chat(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> LLMResponse:
        client = await self._get_client()
        payload = {
            "model": self._model,
            "messages": self._format_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        payload.update(kwargs)

        resp = await client.post("/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()

        choice = data["choices"][0]
        usage = data.get("usage", {})

        return LLMResponse(
            content=choice["message"]["content"],
            model=data.get("model", self._model),
            provider="openai",
            usage={
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
            finish_reason=choice.get("finish_reason", "stop"),
            tool_calls=choice["message"].get("tool_calls", []),
        )

    async def stream(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        client = await self._get_client()
        payload = {
            "model": self._model,
            "messages": self._format_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        payload.update(kwargs)

        async with client.stream("POST", "/chat/completions", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: ") and line != "data: [DONE]":
                    import json
                    chunk = json.loads(line[6:])
                    delta = chunk["choices"][0].get("delta", {})
                    if "content" in delta:
                        yield delta["content"]

    async def count_tokens(self, messages: list[LLMMessage]) -> int:
        try:
            import tiktoken
            encoding = tiktoken.encoding_for_model(self._model)
            total = 0
            for msg in messages:
                total += 4  # message overhead
                total += len(encoding.encode(msg.content))
            return total + 2  # priming tokens
        except ImportError:
            # Fallback to heuristic
            return sum(len(m.content) // 4 + 1 for m in messages)

    async def health_check(self) -> bool:
        try:
            client = await self._get_client()
            resp = await client.get("/models")
            return resp.status_code == 200
        except Exception:
            return False
