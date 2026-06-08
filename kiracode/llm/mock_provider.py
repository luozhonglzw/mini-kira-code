"""Mock LLM Provider — for testing and development without API keys.

Design decisions:
- Returns deterministic responses based on input patterns.
- Simulates token usage for budget management testing.
- Supports configurable latency simulation.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator

from kiracode.llm.base import LLMMessage, LLMProvider, LLMResponse


class MockProvider(LLMProvider):
    """Mock provider for testing. Returns template-based responses."""

    def __init__(self, model: str = "mock-model", latency_ms: int = 0, **kwargs: Any) -> None:
        super().__init__(model, **kwargs)
        self._latency_ms = latency_ms
        self._call_count = 0

    async def chat(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> LLMResponse:
        if self._latency_ms > 0:
            await asyncio.sleep(self._latency_ms / 1000)

        self._call_count += 1
        last_msg = messages[-1].content if messages else ""

        # Generate a deterministic response based on input
        response_text = f"[Mock LLM Response #{self._call_count}]\n"
        response_text += f"Input received: {last_msg[:100]}...\n"
        response_text += "This is a mock response for development/testing."

        prompt_tokens = sum(len(m.content) // 4 + 1 for m in messages)
        completion_tokens = len(response_text) // 4 + 1

        return LLMResponse(
            content=response_text,
            model=self._model,
            provider="mock",
            usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
            finish_reason="stop",
        )

    async def stream(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        response = await self.chat(messages, temperature, max_tokens, **kwargs)
        words = response.content.split()
        for word in words:
            yield word + " "
            if self._latency_ms > 0:
                await asyncio.sleep(self._latency_ms / 1000 / len(words))

    async def count_tokens(self, messages: list[LLMMessage]) -> int:
        return sum(len(m.content) // 4 + 1 for m in messages)

    @property
    def call_count(self) -> int:
        return self._call_count
