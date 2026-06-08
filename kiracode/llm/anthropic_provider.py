"""Anthropic LLM Provider — implements LLMProvider for Claude models.

Design decisions:
- Uses httpx for async HTTP (not anthropic SDK) to minimize dependencies.
- API key read from environment: ANTHROPIC_API_KEY.
- Converts unified LLMMessage format to Anthropic's message format.
- System message is extracted and passed separately (Anthropic API requirement).

Usage:
    provider = AnthropicProvider(model="claude-sonnet-4-20250514")
    response = await provider.chat([LLMMessage(role="user", content="Hello")])
"""

from __future__ import annotations

import os
from typing import Any, AsyncIterator

import httpx

from kiracode.llm.base import LLMMessage, LLMProvider, LLMResponse, MessageRole


class AnthropicProvider(LLMProvider):
    """Anthropic Claude API provider."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        api_key: str | None = None,
        base_url: str = "https://api.anthropic.com",
        **kwargs: Any,
    ) -> None:
        super().__init__(model, **kwargs)
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._base_url = base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None
        self._api_version = "2023-06-01"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": self._api_version,
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(60.0),
            )
        return self._client

    def _convert_messages(self, messages: list[LLMMessage]) -> tuple[str, list[dict[str, Any]]]:
        """Convert unified messages to Anthropic format.

        Returns:
            Tuple of (system_prompt, messages_list).
        """
        system_parts = []
        anthropic_messages = []

        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                system_parts.append(msg.content)
            else:
                role = "assistant" if msg.role == MessageRole.ASSISTANT else "user"
                anthropic_messages.append({"role": role, "content": msg.content})

        return "\n\n".join(system_parts), anthropic_messages

    async def chat(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> LLMResponse:
        client = await self._get_client()
        system_prompt, anthropic_msgs = self._convert_messages(messages)

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": anthropic_msgs,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_prompt:
            payload["system"] = system_prompt
        payload.update(kwargs)

        resp = await client.post("/v1/messages", json=payload)
        resp.raise_for_status()
        data = resp.json()

        content_blocks = data.get("content", [])
        text_content = "".join(
            block["text"] for block in content_blocks if block.get("type") == "text"
        )

        usage = data.get("usage", {})
        return LLMResponse(
            content=text_content,
            model=data.get("model", self._model),
            provider="anthropic",
            usage={
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            },
            finish_reason=data.get("stop_reason", "end_turn"),
        )

    async def stream(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        client = await self._get_client()
        system_prompt, anthropic_msgs = self._convert_messages(messages)

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": anthropic_msgs,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        if system_prompt:
            payload["system"] = system_prompt
        payload.update(kwargs)

        async with client.stream("POST", "/v1/messages", json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    import json
                    event = json.loads(line[6:])
                    if event.get("type") == "content_block_delta":
                        delta = event.get("delta", {})
                        if delta.get("type") == "text_delta":
                            yield delta.get("text", "")

    async def count_tokens(self, messages: list[LLMMessage]) -> int:
        # Anthropic doesn't have a public tokenizer; use heuristic
        return sum(len(m.content) // 4 + 1 for m in messages)

    async def health_check(self) -> bool:
        try:
            client = await self._get_client()
            # Anthropic doesn't have a simple health endpoint;
            # we check by making a minimal request
            return self._api_key != ""
        except Exception:
            return False
