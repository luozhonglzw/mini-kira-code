"""Phase 2 Step 2 — Memory Flow Demo.

Simulates the full lifecycle:
  user query → architect plan → working memory → coder execution
  → episodic memory → consolidate → semantic memory

Run:  python demo_memory.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Force UTF-8 on Windows to avoid GBK encoding errors
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

sys.path.insert(0, str(Path(__file__).parent))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from kiracode.memory.episodic import TaskRecord
from kiracode.memory.manager import MemoryManager
from kiracode.memory.working import Message, MessageRole

console = Console()


# ── helpers ────────────────────────────────────────────────────────────────


def section(title: str) -> None:
    console.print(f"\n[bold cyan]{'─' * 60}[/bold cyan]")
    console.print(f"[bold cyan]  {title}[/bold cyan]")
    console.print(f"[bold cyan]{'─' * 60}[/bold cyan]\n")


def dump_json(data: object) -> None:
    console.print_json(json.dumps(data, indent=2, ensure_ascii=False, default=str))


# ── mock agents (lightweight, inline) ──────────────────────────────────────


def mock_architect_plan(query: str) -> list[dict[str, str]]:
    """Simulate an Architect decomposing a query into subtasks."""
    return [
        {
            "task_id": "sub-001",
            "agent": "coder",
            "description": f"Write input validation for: {query}",
            "target_file": "auth/login.py",
        },
        {
            "task_id": "sub-002",
            "agent": "coder",
            "description": f"Implement core logic for: {query}",
            "target_file": "auth/login.py",
        },
        {
            "task_id": "sub-003",
            "agent": "reviewer",
            "description": f"Review generated code for: {query}",
            "target_file": "auth/login.py",
        },
    ]


def mock_coder_execute(task: dict[str, str]) -> dict[str, str]:
    """Simulate a Coder producing code for a subtask."""
    if "validation" in task["description"].lower():
        return {
            "file": task["target_file"],
            "code": (
                "def validate_login_input(username: str, password: str) -> tuple[bool, str]:\n"
                "    if not username or len(username) < 3:\n"
                '        return False, "Username must be at least 3 characters"\n'
                "    if not password or len(password) < 8:\n"
                '        return False, "Password must be at least 8 characters"\n'
                "    return True, ''"
            ),
            "lines": "6",
        }
    return {
        "file": task["target_file"],
        "code": (
            "def login(username: str, password: str) -> dict:\n"
            "    ok, err = validate_login_input(username, password)\n"
            "    if not ok:\n"
            '        return {"success": False, "error": err}\n'
            "    # TODO: verify credentials against DB\n"
            '    return {"success": True, "token": "mock-jwt-token"}'
        ),
        "lines": "6",
    }


# ── main demo ──────────────────────────────────────────────────────────────


def main() -> None:
    console.print(
        Panel(
            "[bold]KiraCode — Memory Flow Demo[/bold]\n"
            "Simulates: query → plan → working memory → execution\n"
            "→ episodic memory → consolidate → semantic memory",
            border_style="bright_blue",
        )
    )

    mgr = MemoryManager()
    user_query = "帮我写一个带输入校验的 Python 登录函数"

    # ── (a) 用户输入 ────────────────────────────────────────────────────
    section("(a) User Query")
    console.print(f"[yellow]User:[/yellow] {user_query}")
    mgr.remember_message(Message(role=MessageRole.USER, content=user_query))

    # ── (b) Architect 生成 Plan ─────────────────────────────────────────
    section("(b) Architect → TaskPlan")
    plan = mock_architect_plan(user_query)
    plan_text = json.dumps(plan, ensure_ascii=False, indent=2)
    console.print("[green]Architect generated plan:[/green]")
    dump_json(plan)

    # ── (c) Plan 存入 Working Memory ────────────────────────────────────
    section("(c) Working Memory ← Plan")
    mgr.remember_message(
        Message(role=MessageRole.ASSISTANT, content=f"TaskPlan:\n{plan_text}")
    )
    console.print("Plan recorded in working memory.")
    dump_json(mgr.working.summary())

    # ── (d) Coder 执行子任务 ────────────────────────────────────────────
    section("(d) Coder Executes Subtasks")
    executed_tasks: list[TaskRecord] = []
    for subtask in plan:
        console.print(f"\n[bold]→ Running {subtask['task_id']}[/bold] ({subtask['agent']})")
        console.print(f"  Description: {subtask['description']}")

        rec = TaskRecord(
            task_id=subtask["task_id"],
            task_type=(
                "code_generation" if subtask["agent"] == "coder" else "code_review"
            ),
            description=subtask["description"],
            agent_name=subtask["agent"],
            input_data=subtask,
        )
        rec.mark_running()

        if subtask["agent"] == "coder":
            output = mock_coder_execute(subtask)
            rec.mark_success(output=output)
            console.print(f"  [green]✓[/green] Generated {output['lines']} lines → {output['file']}")
        else:
            rec.mark_success(output={"verdict": "pass", "comments": "Looks good, no issues found."})
            console.print("  [green]✓[/green] Review passed")

        executed_tasks.append(rec)

    # ── (e) 执行轨迹存入 Episodic Memory ────────────────────────────────
    section("(e) Episodic Memory ← Execution Traces")
    for rec in executed_tasks:
        mgr.remember_task(rec)
    console.print(f"Stored {len(executed_tasks)} task records in episodic memory.")
    dump_json(mgr.episodic.summary())

    # ── (f) Consolidate：提炼语义记忆 ──────────────────────────────────
    section("(f) Consolidate → Semantic Memory")
    result = mgr.consolidate()
    console.print("[bold]Consolidation result:[/bold]")
    dump_json(result)

    # ── (g) 三层记忆最终状态 ────────────────────────────────────────────
    section("(g) Final Memory State")

    table = Table(title="Memory Layers", show_lines=True)
    table.add_column("Layer", style="cyan")
    table.add_column("Metric", style="white")
    table.add_column("Value", style="green")
    summary = mgr.full_summary()
    for layer, stats in summary.items():
        for k, v in stats.items():
            table.add_row(layer, k, str(v))
    console.print(table)

    # Semantic memory content
    console.print("\n[bold]Semantic Memory Entries:[/bold]")
    for entry in mgr.semantic.entries:
        console.print(f"  • [cyan]{entry.title}[/cyan] (confidence={entry.confidence})")
        console.print(f"    {entry.content[:120]}")

    # Graph edges
    console.print("\n[bold]Memory Graph Edges:[/bold]")
    for src, tgt, data in mgr.graph._graph.edges(data=True):
        console.print(f"  {src} --[{data.get('relation')}]--> {tgt}")

    console.print(
        "\n[bold green]✓ Demo complete. Three-layer memory system fully operational.[/bold green]"
    )


if __name__ == "__main__":
    main()
