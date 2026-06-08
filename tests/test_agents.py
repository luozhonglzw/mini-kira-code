"""Tests for Agent base and Architect/Coder/Reviewer agents."""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kiracode.agents.architect import ArchitectAgent, CoderAgent, ReviewerAgent, SubTask, TaskPlan
from kiracode.agents.base import Agent, AgentContext, AgentResult, AgentState
from kiracode.core.event_bus import EventBus
from kiracode.memory.manager import MemoryManager


# ── State Machine Tests ────────────────────────────────────────────────────


@pytest.mark.unit
class TestStateMachine:
    def test_valid_transitions(self):
        agent = ArchitectAgent()
        assert agent.state == AgentState.IDLE
        agent._transition(AgentState.PLANNING)
        assert agent.state == AgentState.PLANNING
        agent._transition(AgentState.EXECUTING)
        assert agent.state == AgentState.EXECUTING
        agent._transition(AgentState.DONE)
        assert agent.state == AgentState.DONE

    def test_invalid_transition_raises(self):
        agent = ArchitectAgent()
        with pytest.raises(ValueError, match="Invalid state transition"):
            agent._transition(AgentState.EXECUTING)

    def test_reset(self):
        agent = ArchitectAgent()
        agent._transition(AgentState.PLANNING)
        agent.reset()
        assert agent.state == AgentState.IDLE


# ── Architect Tests ────────────────────────────────────────────────────────


@pytest.mark.unit
class TestArchitect:
    def test_plan_output(self):
        async def run():
            architect = ArchitectAgent()
            memory = MemoryManager()
            bus = EventBus()
            ctx = AgentContext(
                query="帮我写一个带输入校验的 Python 登录函数",
                task_id="test-001",
                memory=memory,
                event_bus=bus,
            )
            result = await architect.run(ctx)

            assert result.success
            assert result.state == AgentState.DONE
            plan = result.output.get("plan", {})
            subtasks = plan.get("subtasks", [])
            assert len(subtasks) >= 2  # at least validation + core logic

            # Check subtask structure
            for st in subtasks:
                assert "task_id" in st
                assert "agent_type" in st
                assert "description" in st
                assert st["agent_type"] in ("coder", "reviewer", "security_auditor")

            # Check execution order
            order = result.output.get("execution_order", [])
            assert len(order) >= 1

            return result

        asyncio.run(run())

    def test_plan_with_memory(self):
        async def run():
            architect = ArchitectAgent()
            memory = MemoryManager()
            ctx = AgentContext(
                query="写一个排序算法",
                task_id="test-002",
                memory=memory,
            )
            await architect.run(ctx)
            # Working memory should have the plan
            assert memory.working.summary()["message_count"] >= 1

        asyncio.run(run())


# ── Coder Tests ────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestCoder:
    def test_code_generation(self):
        async def run():
            coder = CoderAgent()
            ctx = AgentContext(
                query="Write input validation for login",
                task_id="test-coder-001",
            )
            result = await coder.run(ctx)
            assert result.success
            code = result.output.get("code", "")
            assert len(code) > 0
            assert result.output.get("lines", 0) > 0
            return result

        asyncio.run(run())

    def test_coder_reuse(self):
        """Agent should auto-reset on each run()."""
        async def run():
            coder = CoderAgent()
            ctx1 = AgentContext(query="task 1", task_id="t1")
            ctx2 = AgentContext(query="task 2", task_id="t2")
            r1 = await coder.run(ctx1)
            r2 = await coder.run(ctx2)
            assert r1.success
            assert r2.success

        asyncio.run(run())


# ── Reviewer Tests ─────────────────────────────────────────────────────────


@pytest.mark.unit
class TestReviewer:
    def test_review_output(self):
        async def run():
            reviewer = ReviewerAgent()
            ctx = AgentContext(
                query="Review this code",
                task_id="test-review-001",
            )
            result = await reviewer.run(ctx)
            assert result.success
            assert result.output.get("verdict") == "pass"
            assert "quality_score" in result.output

        asyncio.run(run())


# ── AgentResult Tests ──────────────────────────────────────────────────────


@pytest.mark.unit
class TestAgentResult:
    def test_success_property(self):
        r = AgentResult(agent_name="test", task_id="t1", state=AgentState.DONE)
        assert r.success is True
        r2 = AgentResult(agent_name="test", task_id="t1", state=AgentState.FAILED)
        assert r2.success is False

    def test_duration_calculation(self):
        from datetime import datetime, timezone, timedelta
        start = datetime.now(timezone.utc)
        end = start + timedelta(milliseconds=150)
        r = AgentResult(
            agent_name="test",
            task_id="t1",
            state=AgentState.DONE,
            started_at=start,
            finished_at=end,
        )
        assert r.duration_ms is not None
        assert 140 <= r.duration_ms <= 160


# ── TaskPlan Tests ─────────────────────────────────────────────────────────


@pytest.mark.unit
class TestTaskPlan:
    def test_execution_order(self):
        plan = TaskPlan(query="test", subtasks=[
            SubTask(task_id="a", agent_type="coder", description="step 1"),
            SubTask(task_id="b", agent_type="coder", description="step 2", depends_on=["a"]),
            SubTask(task_id="c", agent_type="coder", description="step 3", depends_on=["a"]),
            SubTask(task_id="d", agent_type="reviewer", description="review", depends_on=["b", "c"]),
        ])
        order = plan.get_execution_order()
        assert len(order) == 3
        assert order[0] == ["a"]
        assert set(order[1]) == {"b", "c"}
        assert order[2] == ["d"]

    def test_empty_plan(self):
        plan = TaskPlan(query="test")
        assert plan.get_execution_order() == []
        assert plan.task_count == 0
