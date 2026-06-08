"""Tests for core modules: EventBus, TokenBudgetManager, Config."""

from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kiracode.core.config import KiraConfig, load_config
from kiracode.core.event_bus import AgentEvent, Event, EventBus, SystemEvent
from kiracode.core.token_budget import BudgetLevel, TokenBudgetManager


# ── EventBus Tests ─────────────────────────────────────────────────────────


@pytest.mark.unit
class TestEventBus:
    def test_subscribe_and_publish(self):
        bus = EventBus()
        results: list[str] = []

        async def handler(event: Event):
            results.append(event.type)

        bus.subscribe("test.event", handler)

        async def run():
            count = await bus.emit("test.event", {"key": "value"})
            assert count == 1
            assert "test.event" in results

        asyncio.run(run())

    def test_wildcard_subscription(self):
        bus = EventBus()
        events: list[str] = []

        async def wildcard(event: Event):
            events.append(event.type)

        bus.subscribe("*", wildcard)

        async def run():
            await bus.emit("event.a")
            await bus.emit("event.b")
            assert len(events) == 2
            assert events == ["event.a", "event.b"]

        asyncio.run(run())

    def test_multiple_handlers(self):
        bus = EventBus()
        call_count = 0

        async def h1(event: Event):
            nonlocal call_count
            call_count += 1

        async def h2(event: Event):
            nonlocal call_count
            call_count += 1

        bus.subscribe("multi", h1)
        bus.subscribe("multi", h2)

        async def run():
            count = await bus.emit("multi")
            assert count == 2
            assert call_count == 2

        asyncio.run(run())

    def test_handler_error_isolation(self):
        bus = EventBus()
        success_called = False

        async def bad_handler(event: Event):
            raise RuntimeError("boom")

        async def good_handler(event: Event):
            nonlocal success_called
            success_called = True

        bus.subscribe("test", bad_handler)
        bus.subscribe("test", good_handler)

        async def run():
            count = await bus.emit("test")
            assert count == 1  # only good_handler counted
            assert success_called

        asyncio.run(run())

    def test_history(self):
        bus = EventBus()

        async def run():
            await bus.emit("a")
            await bus.emit("b")
            await bus.emit("c")
            history = bus.get_history(limit=10)
            assert len(history) == 3
            assert history[0].type == "a"
            assert history[-1].type == "c"

        asyncio.run(run())

    def test_unsubscribe(self):
        bus = EventBus()
        called = False

        async def handler(event: Event):
            nonlocal called
            called = True

        bus.subscribe("test", handler)
        assert bus.unsubscribe("test", handler) is True
        assert bus.unsubscribe("test", handler) is False

        async def run():
            await bus.emit("test")
            assert not called

        asyncio.run(run())

    def test_summary(self):
        bus = EventBus()
        bus.subscribe("a", lambda e: None)
        bus.subscribe("b", lambda e: None)
        s = bus.summary()
        assert s["subscriber_count"] == 2
        assert set(s["event_types"]) == {"a", "b"}


# ── TokenBudgetManager Tests ───────────────────────────────────────────────


@pytest.mark.unit
class TestTokenBudgetManager:
    def test_default_allocations(self):
        mgr = TokenBudgetManager(total=10000)
        allocs = mgr.list_allocations()
        names = {a.name for a in allocs}
        assert names == {"system", "agent", "tool", "reserve"}
        assert mgr.total == 10000

    def test_consume_and_release(self):
        mgr = TokenBudgetManager(total=10000)
        assert mgr.consume("agent", 3000) is True
        alloc = mgr.get_allocation("agent")
        assert alloc is not None
        assert alloc.used == 3000
        assert alloc.remaining == mgr._allocations["agent"].limit - 3000

        mgr.release("agent", 1000)
        assert alloc.used == 2000

    def test_budget_levels(self):
        mgr = TokenBudgetManager(total=10000, warning_threshold=0.8, hard_limit=0.9)
        alloc = mgr.get_allocation("agent")
        assert alloc is not None
        assert alloc.level == BudgetLevel.NORMAL

        # Consume to warning
        mgr.consume("agent", int(alloc.limit * 0.85))
        assert alloc.level == BudgetLevel.WARNING

    def test_reset(self):
        mgr = TokenBudgetManager(total=10000)
        mgr.consume("agent", 5000)
        mgr.consume("tool", 3000)
        mgr.reset("agent")
        assert mgr.get_allocation("agent").used == 0
        assert mgr.get_allocation("tool").used == 3000

        mgr.reset()
        for a in mgr.list_allocations():
            assert a.used == 0

    def test_snapshot(self):
        mgr = TokenBudgetManager(total=10000)
        mgr.consume("agent", 2000)
        snap = mgr.snapshot()
        assert snap.total_used == 2000
        assert snap.total_remaining == 8000
        assert "agent" in snap.allocations
        assert snap.allocations["agent"]["used"] == 2000

    def test_unknown_allocation(self):
        mgr = TokenBudgetManager(total=10000)
        assert mgr.consume("nonexistent", 100) is False


# ── Config Tests ───────────────────────────────────────────────────────────


@pytest.mark.unit
class TestConfig:
    def test_load_default_config(self):
        cfg = load_config()
        assert cfg.app.name == "KiraCode"
        assert cfg.llm.provider == "mimo"
        assert cfg.agents.architect.enabled is True
        assert cfg.token_budget.total == 128000
        assert cfg.security.sandbox.timeout == 30

    def test_config_nested_values(self):
        cfg = load_config()
        assert cfg.memory.episodic_memory.max_entries == 1000
        assert cfg.memory.graph.enabled is True
        assert cfg.security.secrets_scanner.entropy_threshold == 4.5
        assert cfg.skills.rag.top_k == 5

    def test_config_from_dict(self):
        cfg = KiraConfig(app={"name": "TestApp", "log_level": "DEBUG"})
        assert cfg.app.name == "TestApp"
        assert cfg.app.log_level == "DEBUG"
        # Other fields should have defaults
        assert cfg.llm.provider == "mimo"
