"""Architect Agent — task decomposition and planning.

Design decisions:
- Receives a user query, decomposes it into a TaskPlan (subtask list).
- Each subtask specifies: target agent type, description, dependencies, input.
- Uses Mock LLM for offline operation — a real system would call an LLM API.
- Planning strategy: "decompose" (single-pass) or "incremental" (refine iteratively).
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field

from kiracode.agents.base import Agent, AgentContext, AgentResult, AgentState


# ── Task Plan models ───────────────────────────────────────────────────────


class SubTask(BaseModel):
    task_id: str = Field(default_factory=lambda: f"st-{uuid.uuid4().hex[:8]}")
    agent_type: str  # "coder" | "reviewer" | "security_auditor"
    description: str
    depends_on: list[str] = Field(default_factory=list)
    input_data: dict[str, Any] = Field(default_factory=dict)
    priority: int = 0  # higher = more urgent


class TaskPlan(BaseModel):
    plan_id: str = Field(default_factory=lambda: f"plan-{uuid.uuid4().hex[:8]}")
    query: str = ""
    subtasks: list[SubTask] = Field(default_factory=list)
    strategy: str = "decompose"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def task_count(self) -> int:
        return len(self.subtasks)

    def get_execution_order(self) -> list[list[str]]:
        """Return task IDs grouped by dependency level (parallelizable within group)."""
        if not self.subtasks:
            return []

        task_map = {t.task_id: t for t in self.subtasks}
        levels: list[list[str]] = []
        assigned: set[str] = set()

        while len(assigned) < len(self.subtasks):
            current_level = []
            for task in self.subtasks:
                if task.task_id in assigned:
                    continue
                # All dependencies must be in previous levels
                if all(dep in assigned for dep in task.depends_on):
                    current_level.append(task.task_id)
            if not current_level:
                # Circular dependency or error — assign remaining
                current_level = [
                    t.task_id for t in self.subtasks if t.task_id not in assigned
                ]
            levels.append(current_level)
            assigned.update(current_level)

        return levels


# ── Mock LLM for planning ──────────────────────────────────────────────────


def _mock_plan_decompose(query: str) -> TaskPlan:
    """Mock planning: decompose a query into subtasks.

    This simulates what an LLM-based planner would do.
    In production, this would be replaced with an actual LLM call.
    """
    query_lower = query.lower()

    # Pattern matching for common task types
    subtasks: list[SubTask] = []

    # Always start with validation if the query mentions input/data/form
    if any(kw in query_lower for kw in ["input", "valid", "校验", "验证", "form", "login", "登录"]):
        subtasks.append(
            SubTask(
                agent_type="coder",
                description=f"Write input validation logic for: {query}",
                priority=2,
            )
        )

    # Core implementation
    subtasks.append(
        SubTask(
            agent_type="coder",
            description=f"Implement core logic for: {query}",
            depends_on=[subtasks[0].task_id] if subtasks else [],
            priority=1,
        )
    )

    # Add tests if mentioned
    if any(kw in query_lower for kw in ["test", "测试", "verify", "验证"]):
        subtasks.append(
            SubTask(
                agent_type="coder",
                description=f"Write unit tests for: {query}",
                depends_on=[subtasks[-1].task_id],
                priority=0,
            )
        )

    # Security review
    if any(kw in query_lower for kw in ["security", "安全", "auth", "login", "登录", "密码", "password"]):
        subtasks.append(
            SubTask(
                agent_type="security_auditor",
                description=f"Security audit for: {query}",
                depends_on=[subtasks[-1].task_id],
                priority=3,
            )
        )

    # Always end with code review
    subtasks.append(
        SubTask(
            agent_type="reviewer",
            description=f"Review generated code for: {query}",
            depends_on=[s.task_id for s in subtasks],
            priority=0,
        )
    )

    return TaskPlan(query=query, subtasks=subtasks, strategy="decompose")


# ── Architect Agent ────────────────────────────────────────────────────────


class ArchitectAgent(Agent):
    """Decomposes user queries into executable task plans."""

    def __init__(self, max_subtasks: int = 10) -> None:
        super().__init__("architect")
        self._max_subtasks = max_subtasks

    async def plan(self, ctx: AgentContext) -> dict[str, Any]:
        """Analyze the query — no sub-planning needed for architect."""
        self._logger.info("Architect analyzing query: %s", ctx.query[:80])
        return {"phase": "analysis", "query_length": len(ctx.query)}

    async def execute(self, ctx: AgentContext) -> dict[str, Any]:
        """Decompose the query into a TaskPlan."""
        self._logger.info("Architect decomposing query into task plan")

        # Use mock planner
        plan = _mock_plan_decompose(ctx.query)

        # Enforce max subtasks
        if len(plan.subtasks) > self._max_subtasks:
            plan.subtasks = plan.subtasks[: self._max_subtasks]

        # Store plan in working memory if available
        if ctx.memory is not None:
            from kiracode.memory.working import Message, MessageRole
            import json
            plan_text = json.dumps(
                {"plan_id": plan.plan_id, "subtasks": [s.model_dump() for s in plan.subtasks]},
                ensure_ascii=False,
                indent=2,
            )
            ctx.memory.remember_message(
                Message(role=MessageRole.ASSISTANT, content=f"[TaskPlan]\n{plan_text}")
            )

        execution_order = plan.get_execution_order()

        return {
            "plan": plan.model_dump(),
            "execution_order": execution_order,
            "subtask_count": len(plan.subtasks),
        }

    async def review(self, ctx: AgentContext, result: AgentResult) -> bool:
        """Quick sanity check on the plan."""
        plan_data = result.output.get("plan", {})
        subtasks = plan_data.get("subtasks", [])
        if not subtasks:
            result.error = "Plan has no subtasks"
            return False
        return True  # enter REVIEWING state briefly


# ── Coder Agent (stub) ────────────────────────────────────────────────────


class CoderAgent(Agent):
    """Generates code based on a task description. Mock implementation."""

    def __init__(self) -> None:
        super().__init__("coder")

    async def plan(self, ctx: AgentContext) -> dict[str, Any]:
        return {"phase": "code_analysis", "target": ctx.metadata.get("target_file", "")}

    async def execute(self, ctx: AgentContext) -> dict[str, Any]:
        description = ctx.query or ctx.metadata.get("description", "")
        # Mock code generation
        code = self._mock_generate(description)
        return {
            "code": code,
            "language": "python",
            "lines": len(code.split("\n")),
        }

    def _mock_generate(self, description: str) -> str:
        desc_lower = description.lower()
        if "valid" in desc_lower or "校验" in desc_lower:
            return (
                "def validate_input(data: dict) -> tuple[bool, str]:\n"
                '    if not data.get("username"):\n'
                '        return False, "Username is required"\n'
                '    if not data.get("password") or len(data["password"]) < 8:\n'
                '        return False, "Password must be at least 8 characters"\n'
                "    return True, ''"
            )
        elif "login" in desc_lower or "登录" in desc_lower:
            return (
                "def login(username: str, password: str) -> dict:\n"
                "    ok, err = validate_input({'username': username, 'password': password})\n"
                "    if not ok:\n"
                '        return {"success": False, "error": err}\n'
                '    return {"success": True, "token": "mock-jwt-token"}'
            )
        else:
            return (
                f"# Implementation for: {description[:60]}\n"
                "def process(data: dict) -> dict:\n"
                '    """Auto-generated implementation."""\n'
                "    return {'status': 'ok', 'data': data}"
            )


# ── Reviewer Agent (stub) ─────────────────────────────────────────────────


class ReviewerAgent(Agent):
    """Reviews code quality. Mock implementation."""

    def __init__(self) -> None:
        super().__init__("reviewer")

    async def plan(self, ctx: AgentContext) -> dict[str, Any]:
        return {"phase": "review_setup"}

    async def execute(self, ctx: AgentContext) -> dict[str, Any]:
        return {
            "verdict": "pass",
            "issues": [],
            "suggestions": ["Consider adding type hints", "Add docstrings"],
            "quality_score": 8.5,
        }
