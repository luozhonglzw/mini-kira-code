"""Async Event Bus — publish/subscribe with typed events.

Design decisions:
- Fully async (asyncio).
- Events are Pydantic models with a type string discriminator.
- Handlers are async callables: async def handler(event: Event) -> None.
- Supports wildcard subscriptions ("*" matches all event types).
- Handler execution order is FIFO per event type.
- Errors in handlers are caught and logged, never crash the bus.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ── Event model ────────────────────────────────────────────────────────────


class Event(BaseModel):
    """Base event. Subclass for specific event types."""

    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    source: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def __str__(self) -> str:
        return f"Event({self.type}, source={self.source})"


# Predefined event types
class AgentEvent(Event):
    """Events emitted by agents."""
    type: str = "agent"
    agent_name: str = ""

    def model_post_init(self, __context: Any) -> None:
        if not self.source:
            self.source = self.agent_name


class TaskEvent(Event):
    """Events related to task lifecycle."""
    type: str = "task"
    task_id: str = ""


class SystemEvent(Event):
    """System-level events (startup, shutdown, budget warning)."""
    type: str = "system"


# ── Handler type ───────────────────────────────────────────────────────────

EventHandler = Callable[[Event], Coroutine[Any, Any, None]]


# ── EventBus ───────────────────────────────────────────────────────────────


class EventBus:
    """Async publish/subscribe event bus."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = {}
        self._history: list[Event] = []
        self._max_history: int = 1000

    # -- subscribe / unsubscribe ------------------------------------------

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Register a handler for an event type. Use '*' for all events."""
        self._handlers.setdefault(event_type, []).append(handler)
        logger.debug("Subscribed %s to '%s'", handler.__name__, event_type)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> bool:
        """Remove a handler. Returns True if found."""
        handlers = self._handlers.get(event_type, [])
        try:
            handlers.remove(handler)
            return True
        except ValueError:
            return False

    # -- publish -----------------------------------------------------------

    async def publish(self, event: Event) -> int:
        """Publish an event. Returns number of handlers invoked."""
        self._record(event)
        handlers = list(self._handlers.get(event.type, []))
        handlers += self._handlers.get("*", [])

        invoked = 0
        for handler in handlers:
            try:
                await handler(event)
                invoked += 1
            except Exception:
                logger.exception(
                    "Handler %s failed for event %s",
                    handler.__name__,
                    event.type,
                )
        return invoked

    async def emit(self, event_type: str, payload: dict[str, Any] | None = None, source: str = "") -> int:
        """Convenience: create and publish an Event."""
        return await self.publish(Event(type=event_type, payload=payload or {}, source=source))

    # -- history -----------------------------------------------------------

    def _record(self, event: Event) -> None:
        self._history.append(event)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    def get_history(self, event_type: str | None = None, limit: int = 50) -> list[Event]:
        events = self._history
        if event_type:
            events = [e for e in events if e.type == event_type]
        return events[-limit:]

    # -- stats -------------------------------------------------------------

    @property
    def subscriber_count(self) -> int:
        return sum(len(h) for h in self._handlers.values())

    def summary(self) -> dict[str, Any]:
        return {
            "subscriber_count": self.subscriber_count,
            "event_types": list(self._handlers.keys()),
            "history_size": len(self._history),
        }
