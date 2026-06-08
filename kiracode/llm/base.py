"""LLM Base — abstract provider interface for language model integration.

Design decisions:
- Async-first: all LLM calls are async for non-blocking execution.
- Unified message format across providers (OpenAI, Anthropic, etc.).
- Streaming support via async generator.
- Token counting delegated to provider-specific implementations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, AsyncIterator

from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class LLMMessage(BaseModel):
    """Unified message format across all providers."""

    role: MessageRole
    content: str
    name: str = ""
    tool_call_id: str = ""
    reasoning_content: str | None = None  # MiMo thinking mode trace
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMResponse(BaseModel):
    """Standardized LLM response."""

    content: str
    model: str
    provider: str
    usage: dict[str, int] = Field(default_factory=dict)  # prompt_tokens, completion_tokens, total_tokens
    finish_reason: str = "stop"
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    reasoning_content: str | None = None  # MiMo thinking mode trace
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.usage.get("total_tokens", 0)


class LLMProvider(ABC):
    """Abstract base class for LLM providers.

    Subclasses must implement:
    - chat(): Send messages and get a response.
    - stream(): Send messages and get a streaming response.
    - count_tokens(): Estimate token count for messages.
    """

    def __init__(self, model: str, **kwargs: Any) -> None:
        self._model = model
        self._config = kwargs

    @property
    def model(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return self.__class__.__name__.replace("Provider", "").lower()

    @abstractmethod
    async def chat(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> LLMResponse:
        """Send a chat completion request.

        Args:
            messages: Conversation messages.
            temperature: Sampling temperature (0.0-2.0).
            max_tokens: Maximum tokens in response.
            **kwargs: Provider-specific parameters.

        Returns:
            LLMResponse with generated content and usage stats.
        """
        ...

    @abstractmethod
    async def stream(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Stream a chat completion response.

        Args:
            messages: Conversation messages.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in response.
            **kwargs: Provider-specific parameters.

        Yields:
            Content chunks as they arrive.
        """
        ...
        # Make this an async generator
        yield ""  # pragma: no cover

    @abstractmethod
    async def count_tokens(self, messages: list[LLMMessage]) -> int:
        """Estimate token count for a list of messages.

        Args:
            messages: Messages to count tokens for.

        Returns:
            Estimated token count.
        """
        ...

    async def health_check(self) -> bool:
        """Check if the provider is available and configured correctly.

        Returns:
            True if the provider is healthy.
        """
        return True
