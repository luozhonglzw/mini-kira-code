"""Working Memory — maintains current session context as a message list.

Design decisions:
- Pure Python list, no external DB; session-scoped only.
- Each message tracks its own token count for O(1) budget checks.
- Supports push / pop / truncate_to_budget operations.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, PrivateAttr

from kiracode.utils.token_counter import count_tokens


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class Message(BaseModel):
    role: MessageRole
    content: str
    token_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        if self.token_count == 0:
            self.token_count = count_tokens(self.content)


class WorkingMemory(BaseModel):
    """In-session message buffer with token accounting."""

    messages: list[Message] = Field(default_factory=list)
    max_tokens: int = 128_000

    model_config = {"arbitrary_types_allowed": True}

    _total_tokens: int = PrivateAttr(default=0)

    # -- public API --------------------------------------------------------

    def push(self, message: Message) -> None:
        self.messages.append(message)
        self._total_tokens += message.token_count

    def pop(self) -> Message | None:
        if not self.messages:
            return None
        msg = self.messages.pop()
        self._total_tokens -= msg.token_count
        return msg

    @property
    def total_tokens(self) -> int:
        return self._total_tokens

    @property
    def remaining_tokens(self) -> int:
        return max(0, self.max_tokens - self._total_tokens)

    def truncate_to_budget(self, target_tokens: int) -> list[Message]:
        """Remove oldest messages until total <= target_tokens.
        Returns the evicted messages (oldest first).
        """
        evicted: list[Message] = []
        while self._total_tokens > target_tokens and self.messages:
            evicted.append(self.messages.pop(0))
        self._total_tokens = sum(m.token_count for m in self.messages)
        return evicted

    def get_context_messages(self) -> list[dict[str, str]]:
        """Return messages in the format expected by LLM APIs."""
        return [{"role": m.role.value, "content": m.content} for m in self.messages]

    def clear(self) -> None:
        self.messages.clear()
        self._total_tokens = 0

    def summary(self) -> dict[str, Any]:
        return {
            "message_count": len(self.messages),
            "total_tokens": self._total_tokens,
            "remaining_tokens": self.remaining_tokens,
            "utilization": round(self._total_tokens / self.max_tokens, 3),
        }
