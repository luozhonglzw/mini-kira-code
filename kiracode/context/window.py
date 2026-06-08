"""Context Window Manager — sliding-window message buffer with budget control.

Design decisions:
- Wraps WorkingMemory and adds automatic eviction policy.
- When total tokens exceed *compression_threshold* of the budget, triggers
  the Compressor to shrink older messages before hard-evicting them.
- Keeps the most recent messages untouched (recency bias).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, PrivateAttr

from kiracode.memory.working import Message, MessageRole, WorkingMemory
from kiracode.utils.token_counter import count_tokens


class WindowConfig(BaseModel):
    max_tokens: int = 128_000
    compression_threshold: float = 0.8  # trigger compression at 80%
    min_recent_messages: int = 4  # always keep at least this many recent messages
    strategy: str = "sliding_window"  # sliding_window | smart_compress


class WindowManager(BaseModel):
    """Manages a context window with automatic eviction and compression hooks."""

    config: WindowConfig = Field(default_factory=WindowConfig)
    buffer: WorkingMemory = Field(default_factory=WorkingMemory)

    model_config = {"arbitrary_types_allowed": True}

    _compressor: Any = PrivateAttr(default=None)  # set via set_compressor()

    # -- lifecycle ---------------------------------------------------------

    def set_compressor(self, compressor: Any) -> None:
        """Inject the Compressor (late binding to avoid circular imports)."""
        self._compressor = compressor

    # -- write API ---------------------------------------------------------

    def add_message(self, message: Message) -> list[Message]:
        """Add a message; returns list of evicted messages (if any)."""
        self.buffer.push(message)
        return self._maybe_evict()

    def add_user(self, content: str, **kw: Any) -> list[Message]:
        return self.add_message(Message(role=MessageRole.USER, content=content, **kw))

    def add_assistant(self, content: str, **kw: Any) -> list[Message]:
        return self.add_message(Message(role=MessageRole.ASSISTANT, content=content, **kw))

    def add_tool(self, content: str, **kw: Any) -> list[Message]:
        return self.add_message(Message(role=MessageRole.TOOL, content=content, **kw))

    def add_system(self, content: str, **kw: Any) -> list[Message]:
        return self.add_message(Message(role=MessageRole.SYSTEM, content=content, **kw))

    # -- read API ----------------------------------------------------------

    @property
    def total_tokens(self) -> int:
        return self.buffer.total_tokens

    @property
    def utilization(self) -> float:
        return self.buffer.total_tokens / self.config.max_tokens if self.config.max_tokens else 0.0

    @property
    def message_count(self) -> int:
        return len(self.buffer.messages)

    def get_messages(self) -> list[Message]:
        return list(self.buffer.messages)

    def get_context(self) -> list[dict[str, str]]:
        return self.buffer.get_context_messages()

    # -- eviction ----------------------------------------------------------

    def _maybe_evict(self) -> list[Message]:
        """Check budget and evict if needed. Returns evicted messages."""
        if self.utilization < self.config.compression_threshold:
            return []

        # Try compression first if compressor is available
        if self._compressor is not None:
            compressed = self._compress_old_messages()
            if compressed > 0 and self.utilization < self.config.compression_threshold:
                return []

        # Hard eviction: remove oldest messages beyond min_recent
        target = int(self.config.max_tokens * 0.7)
        evicted = self.buffer.truncate_to_budget(target)
        # Protect recent messages
        protected = self.config.min_recent_messages
        if len(self.buffer.messages) < protected and evicted:
            # put back the last `protected` evicted messages
            to_restore = evicted[-protected:]
            evicted = evicted[:-protected]
            for m in to_restore:
                self.buffer.push(m)
        return evicted

    def _compress_old_messages(self) -> int:
        """Compress old tool messages. Returns number of messages compressed."""
        threshold = getattr(self._compressor.config, "threshold_tokens", 2000)
        compressed = 0
        for i, msg in enumerate(self.buffer.messages):
            if msg.role == MessageRole.TOOL and msg.token_count > threshold:
                result = self._compressor.compress(msg)
                if result.compressed_token_count < msg.token_count:
                    old_tokens = msg.token_count
                    self.buffer.messages[i] = Message(
                        role=msg.role,
                        content=result.summary,
                        metadata={
                            **msg.metadata,
                            "compressed": True,
                            "ref_id": result.ref_id,
                            "original_tokens": old_tokens,
                        },
                    )
                    compressed += 1
        # Recalculate total tokens
        self.buffer._total_tokens = sum(m.token_count for m in self.buffer.messages)
        return compressed

    # -- summary -----------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        return {
            "message_count": self.message_count,
            "total_tokens": self.total_tokens,
            "max_tokens": self.config.max_tokens,
            "utilization": round(self.utilization, 4),
            "compression_threshold": self.config.compression_threshold,
            "strategy": self.config.strategy,
        }
