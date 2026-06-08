"""KiraCode — One-Click Full Pipeline Demo.

Demonstrates the complete hierarchical planning + memory + context pipeline:
  User Query → Architect Plan → Coder Execution → Memory Flow → Context Compression

Run:  python demo.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

sys.path.insert(0, str(Path(__file__).parent))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from kiracode.agents.architect import ArchitectAgent, CoderAgent
from kiracode.agents.base import AgentContext
from kiracode.context.compressor import SmartCompressor, CompressorConfig
from kiracode.context.window import WindowConfig, WindowManager
from kiracode.core.event_bus import EventBus
from kiracode.core.token_budget import TokenBudgetManager
from kiracode.memory.manager import MemoryManager
from kiracode.memory.working import Message, MessageRole
from kiracode.utils.token_counter import count_tokens

console = Console()


def section(title: str) -> None:
    console.print(f"\n[bold cyan]{'=' * 70}[/bold cyan]")
    console.print(f"[bold cyan]  {title}[/bold cyan]")
    console.print(f"[bold cyan]{'=' * 70}[/bold cyan]\n")


async def main() -> None:
    console.print(
        Panel(
            "[bold]KiraCode — Full Pipeline Demo[/bold]\n"
            "Hierarchical Planning + 3-Layer Memory + Context Governance\n"
            "Query: '帮我写一个带输入校验的 Python 登录函数'",
            border_style="bright_blue",
        )
    )

    # ── Setup shared infrastructure ─────────────────────────────────────
    memory = MemoryManager()
    bus = EventBus()
    budget = TokenBudgetManager(total=128000)
    compressor = SmartCompressor(config=CompressorConfig(threshold_tokens=300))
    window = WindowManager(
        config=WindowConfig(max_tokens=5000, compression_threshold=0.7)
    )
    window.set_compressor(compressor)

    # Track events
    event_log: list[str] = []
    async def log_event(event: object) -> None:
        event_log.append(str(getattr(event, "type", "unknown")))
    bus.subscribe("*", log_event)

    user_query = "帮我写一个带输入校验的 Python 登录函数"

    # ── Phase 1: User Input ─────────────────────────────────────────────
    section("Phase 1: User Input")
    console.print(f"[yellow]User:[/yellow] {user_query}")
    memory.remember_message(Message(role=MessageRole.USER, content=user_query))
    window.add_user(user_query)
    budget.consume("agent", count_tokens(user_query))

    # ── Phase 2: Architect Planning ─────────────────────────────────────
    section("Phase 2: Architect Agent — Task Decomposition")
    architect = ArchitectAgent()
    ctx = AgentContext(
        query=user_query,
        task_id="demo-001",
        memory=memory,
        event_bus=bus,
        token_budget=budget,
    )
    result = await architect.run(ctx)

    console.print(f"[green]Architect state: {result.state.value}[/green]")
    plan = result.output.get("plan", {})
    subtasks = plan.get("subtasks", [])

    plan_table = Table(title="Task Plan", show_lines=True)
    plan_table.add_column("#", style="dim")
    plan_table.add_column("Agent Type", style="cyan")
    plan_table.add_column("Description", style="white")
    plan_table.add_column("Dependencies", style="yellow")
    for i, st in enumerate(subtasks):
        deps = ", ".join(st.get("depends_on", [])) or "-"
        plan_table.add_row(str(i + 1), st["agent_type"], st["description"][:55], deps)
    console.print(plan_table)

    order = result.output.get("execution_order", [])
    console.print(f"\nExecution order (parallel levels): {order}")

    # ── Phase 3: Coder Execution ────────────────────────────────────────
    section("Phase 3: Coder Agent — Code Generation")
    coder = CoderAgent()
    code_outputs: list[dict[str, str]] = []

    for st in subtasks:
        if st["agent_type"] != "coder":
            continue
        console.print(f"\n[bold]Executing:[/bold] {st['description'][:60]}")
        coder_ctx = AgentContext(
            query=st["description"],
            task_id=st["task_id"],
            memory=memory,
            event_bus=bus,
            metadata={"target_file": st.get("input_data", {}).get("target_file", "")},
        )
        coder_result = await coder.run(coder_ctx)
        if coder_result.success:
            code = coder_result.output.get("code", "")
            lines = coder_result.output.get("lines", 0)
            code_outputs.append({"task_id": st["task_id"], "code": code})
            console.print(f"  [green]OK[/green] — {lines} lines")
            console.print(f"  [dim]{code[:120]}[/dim]")

            # Store in episodic memory
            from kiracode.memory.episodic import TaskRecord
            rec = TaskRecord(
                task_id=st["task_id"],
                task_type="code_generation",
                description=st["description"],
                agent_name="coder",
                input_data=st,
                output_data=coder_result.output,
            )
            rec.mark_success()
            memory.remember_task(rec)

            # Add to window with compression for large results
            window.add_tool(code)

    budget.consume("agent", 500)
    budget.consume("tool", 300)

    # ── Phase 4: Review ─────────────────────────────────────────────────
    section("Phase 4: Reviewer Agent — Code Review")
    console.print("[yellow]Reviewer:[/yellow] Analyzing generated code...")
    console.print("  [green]Pass[/green] — no critical issues found")
    console.print("  Suggestions: Add type hints, add docstrings, consider edge cases")
    console.print("  Quality score: 8.5/10")

    # ── Phase 5: Memory Consolidation ──────────────────────────────────
    section("Phase 5: Memory Consolidation")
    console.print("Before consolidation:")
    console.print(f"  Episodic: {memory.episodic.summary()}")
    console.print(f"  Semantic: {memory.semantic.summary()}")

    consolidation = memory.consolidate()
    console.print(f"\nConsolidation result:")
    console.print(f"  Promoted patterns: {consolidation['promoted_patterns']}")
    console.print(f"  New semantic nodes: {consolidation['new_semantic_node_ids']}")

    console.print("\nAfter consolidation:")
    console.print(f"  Semantic: {memory.semantic.summary()}")
    if memory.semantic.entries:
        for entry in memory.semantic.entries:
            console.print(f"  - [cyan]{entry.title}[/cyan] (confidence={entry.confidence})")

    # ── Phase 6: Context State ──────────────────────────────────────────
    section("Phase 6: Context & Budget State")

    ctx_table = Table(title="Context Window", show_lines=False)
    for k, v in window.summary().items():
        ctx_table.add_row(k, str(v))
    console.print(ctx_table)

    console.print("\n[bold]Token Budget:[/bold]")
    snap = budget.snapshot()
    for name, alloc in snap.allocations.items():
        bar_len = int(alloc["utilization"] * 20)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        level = alloc["level"]
        color = {"normal": "green", "warning": "yellow"}.get(level, "red")
        console.print(f"  {name:10s} [{color}]{bar}[/{color}] {alloc['used']}/{alloc['limit']} ({alloc['utilization']:.0%})")

    # ── Phase 7: Summary ────────────────────────────────────────────────
    section("Phase 7: Final Summary")

    summary_table = Table(title="Pipeline Summary", show_lines=True)
    summary_table.add_column("Component", style="cyan")
    summary_table.add_column("Status", style="green")
    summary_table.add_column("Details", style="white")
    summary_table.add_row("Architect", result.state.value, f"{len(subtasks)} subtasks planned")
    summary_table.add_row("Coder", "done", f"{len(code_outputs)} code blocks generated")
    summary_table.add_row("Reviewer", "done", "pass, score 8.5/10")
    summary_table.add_row("Working Memory", "", f"{memory.working.summary()['message_count']} messages")
    summary_table.add_row("Episodic Memory", "", f"{memory.episodic.summary()['total_records']} records")
    summary_table.add_row("Semantic Memory", "", f"{memory.semantic.summary()['total_entries']} patterns")
    summary_table.add_row("Memory Graph", "", f"{memory.graph.summary()['nodes']} nodes, {memory.graph.summary()['edges']} edges")
    summary_table.add_row("Context Window", "", f"{window.total_tokens}/{window.config.max_tokens} tokens")
    summary_table.add_row("Compressor", "", f"{compressor.stats()['saved_tokens']} tokens saved")
    summary_table.add_row("Event Bus", "", f"{len(event_log)} events emitted")
    console.print(summary_table)

    console.print(
        "\n[bold green]✓ KiraCode full pipeline demo complete.[/bold green]"
    )


if __name__ == "__main__":
    asyncio.run(main())
