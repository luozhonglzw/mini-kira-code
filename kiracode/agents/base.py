"""Agent Base — abstract base class with lifecycle state machine.

State machine:
  IDLE → PLANNING → EXECUTING → REVIEWING → DONE
                                        ↘ FAILED

Design decisions:
- Agents are async-first: run() is the main entry point.
- State transitions are enforced; invalid transitions raise ValueError.
- Each agent receives a shared AgentContext with access to memory,
  event bus, and token budget.
- AgentResult is the standardized output from any agent.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ── State Machine ──────────────────────────────────────────────────────────


class AgentState(str, Enum):
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    REVIEWING = "reviewing"
    DONE = "done"
    FAILED = "failed"


_VALID_TRANSITIONS: dict[AgentState, set[AgentState]] = {
    AgentState.IDLE: {AgentState.PLANNING},
    AgentState.PLANNING: {AgentState.EXECUTING, AgentState.FAILED},
    AgentState.EXECUTING: {AgentState.REVIEWING, AgentState.DONE, AgentState.FAILED},
    AgentState.REVIEWING: {AgentState.DONE, AgentState.FAILED, AgentState.EXECUTING},
    AgentState.DONE: set(),
    AgentState.FAILED: set(),
}


def validate_transition(current: AgentState, target: AgentState) -> None:
    allowed = _VALID_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise ValueError(
            f"Invalid state transition: {current.value} -> {target.value}. "
            f"Allowed: {[s.value for s in allowed]}"
        )


# ── Context ────────────────────────────────────────────────────────────────


class AgentContext(BaseModel):
    """Shared context available to all agents during execution."""

    query: str = ""
    task_id: str = ""
    parent_task_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Injected by the orchestrator — not serialized
    memory: Any = None
    event_bus: Any = None
    token_budget: Any = None

    model_config = {"arbitrary_types_allowed": True}


# ── Result ─────────────────────────────────────────────────────────────────


class AgentResult(BaseModel):
    """Standardized output from any agent."""

    agent_name: str
    task_id: str
    state: AgentState
    output: dict[str, Any] = Field(default_factory=dict)
    subtasks: list[dict[str, Any]] = Field(default_factory=list)
    token_usage: int = 0
    error: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.state == AgentState.DONE

    @property
    def duration_ms(self) -> float | None:
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds() * 1000
        return None


# ── Agent ABC ──────────────────────────────────────────────────────────────


class Agent(ABC):
    """Abstract base class for all agents.

    Subclasses must implement:
    - plan(ctx) → prepare execution plan
    - execute(ctx) → do the actual work
    - review(ctx, result) → optional quality check
    """

    def __init__(self, name: str) -> None:
        self._name = name
        self._state = AgentState.IDLE
        self._logger = logging.getLogger(f"agent.{name}")

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> AgentState:
        return self._state

    def _transition(self, target: AgentState) -> None:
        validate_transition(self._state, target)
        self._logger.debug("%s: %s -> %s", self._name, self._state.value, target.value)
        self._state = target

    # -- main entry point --------------------------------------------------

    async def run(self, ctx: AgentContext) -> AgentResult:
        """Execute the full agent lifecycle: plan → execute → review."""
        self.reset()  # allow reuse of agent instances
        started = datetime.now(timezone.utc)
        result = AgentResult(
            agent_name=self._name,
            task_id=ctx.task_id,
            state=AgentState.IDLE,
            started_at=started,
        )

        try:
            # Planning phase
            self._transition(AgentState.PLANNING)
            result.state = AgentState.PLANNING
            plan_output = await self.plan(ctx)
            result.output.update(plan_output)

            # Executing phase
            self._transition(AgentState.EXECUTING)
            result.state = AgentState.EXECUTING
            exec_output = await self.execute(ctx)
            result.output.update(exec_output)

            # Reviewing phase (optional)
            should_review = await self.review(ctx, result)
            if should_review:
                self._transition(AgentState.REVIEWING)
                result.state = AgentState.REVIEWING

            # Done
            self._transition(AgentState.DONE)
            result.state = AgentState.DONE

        except Exception as e:
            self._logger.exception("%s failed: %s", self._name, e)
            try:
                self._transition(AgentState.FAILED)
            except ValueError:
                pass  # Already in a terminal state
            result.state = AgentState.FAILED
            result.error = str(e)

        finally:
            result.finished_at = datetime.now(timezone.utc)
            await self._emit_result(ctx, result)

        return result

    # -- lifecycle hooks (override in subclasses) ---------------------------

    @abstractmethod
    async def plan(self, ctx: AgentContext) -> dict[str, Any]:
        """Planning phase: analyze the query and prepare a plan.
        Returns a dict with plan details (merged into AgentResult.output).
        """
        ...

    @abstractmethod
    async def execute(self, ctx: AgentContext) -> dict[str, Any]:
        """Execution phase: do the actual work.
        Returns a dict with execution results.
        """
        ...

    async def review(self, ctx: AgentContext, result: AgentResult) -> bool:
        """Review phase: quality check. Return True to enter REVIEWING state.
        Default: skip review.
        """
        return False

    # -- helpers -----------------------------------------------------------

    async def _emit_result(self, ctx: AgentContext, result: AgentResult) -> None:
        """Publish result to event bus if available."""
        if ctx.event_bus is not None:
            from kiracode.core.event_bus import AgentEvent
            await ctx.event_bus.publish(
                AgentEvent(
                    type=f"agent.{self._name}.completed",
                    agent_name=self._name,
                    payload={
                        "task_id": ctx.task_id,
                        "state": result.state.value,
                        "success": result.success,
                        "duration_ms": result.duration_ms,
                    },
                    source=self._name,
                )
            )

    def reset(self) -> None:
        """Reset agent to IDLE state."""
        self._state = AgentState.IDLE
