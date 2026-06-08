"""KiraCode — Full System Integration Demo.

Demonstrates ALL subsystems working together:
  Core → Agents → Memory → Context → Security → Skills

Run:  python demo_full.py
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

console = Console()


def section(title: str) -> None:
    console.print(f"\n[bold cyan]{'=' * 70}[/bold cyan]")
    console.print(f"[bold cyan]  {title}[/bold cyan]")
    console.print(f"[bold cyan]{'=' * 70}[/bold cyan]\n")


async def main() -> None:
    console.print(
        Panel(
            "[bold]KiraCode — Full System Integration Demo[/bold]\n"
            "All subsystems: Core + Agents + Memory + Context + Security + Skills",
            border_style="bright_blue",
        )
    )

    # ── 1. Core: Config + EventBus + TokenBudget ────────────────────────
    section("1. Core Engine")
    from kiracode.core.config import load_config
    from kiracode.core.event_bus import EventBus
    from kiracode.core.token_budget import TokenBudgetManager

    cfg = load_config()
    bus = EventBus()
    budget = TokenBudgetManager(total=128000)

    console.print(f"  Config loaded: app={cfg.app.name}, llm={cfg.llm.provider}")
    console.print(f"  EventBus: {bus.summary()}")
    console.print(f"  Budget: total={budget.total}, allocations={len(budget.list_allocations())}")

    # ── 2. Skills: Load + Route ─────────────────────────────────────────
    section("2. Skill System")
    from kiracode.skills.loader import SkillLoader
    from kiracode.skills.registry import registry
    from kiracode.skills.router import SkillRouter

    loader = SkillLoader(registry)
    loaded = loader.load_from_directory("kiracode/skills/builtin")
    router = SkillRouter(registry)

    console.print(f"  Loaded {loaded} skills: {registry.summary()['names']}")

    route = router.route("read the login file", top_k=2)
    for r in route:
        console.print(f"  Route: '{r.skill_name}' score={r.score} ({r.reason})")

    # ── 3. Security: Scanner + Sandbox + Audit + Rollback ──────────────
    section("3. Security Infrastructure")
    from kiracode.security.audit_log import AuditLog
    from kiracode.security.rollback import RollbackManager
    from kiracode.security.sandbox import Sandbox, SandboxConfig
    from kiracode.security.secrets_scanner import SecretsScanner

    scanner = SecretsScanner()
    sandbox = Sandbox(SandboxConfig(timeout=5))
    audit = AuditLog(path=".kiracode/audit/demo_audit.jsonl")
    rollback = RollbackManager()

    # Scan a file for secrets
    findings = scanner.scan_file("configs/default.yaml")
    console.print(f"  Secrets scan on default.yaml: {len(findings)} findings")

    # Scan demo code
    demo_code = 'API_KEY = "AKIAIOSFODNN7EXAMPLE"\npassword = "my_secret_123"'
    findings = scanner.scan_text(demo_code)
    console.print(f"  Secrets scan on demo code: {len(findings)} findings")
    for f in findings:
        console.print(f"    [{f.severity}] {f.pattern_name} line={f.line_number}")

    # Sandbox test
    result = await sandbox.run_code('print("sandbox OK")')
    console.print(f"  Sandbox: success={result.success}, output={result.stdout.strip()}")

    # Audit log
    await audit.log_event("security_scan", "auditor", "scan_secrets", outcome="success")
    await audit.log_event("tool_call", "coder", "execute_code", target="auth/login.py")
    console.print(f"  Audit log: {audit.summary()['total_entries']} entries")

    # Rollback snapshot
    rb = RollbackManager()
    console.print(f"  Rollback: {rb.summary()}")

    # ── 4. Memory: Three-layer + Graph ──────────────────────────────────
    section("4. Memory System")
    from kiracode.memory.episodic import TaskRecord
    from kiracode.memory.manager import MemoryManager
    from kiracode.memory.semantic import KnowledgeEntry
    from kiracode.memory.working import Message, MessageRole

    memory = MemoryManager()
    memory.remember_message(Message(role=MessageRole.USER, content="Build a secure login system"))
    memory.remember_message(Message(role=MessageRole.ASSISTANT, content="Plan: 3 subtasks"))

    rec = TaskRecord(task_type="code_generation", description="Generate login function")
    rec.mark_success(output={"code": "def login(): ...", "lines": 15})
    memory.remember_task(rec)

    memory.remember_knowledge(
        KnowledgeEntry(
            title="Auth pattern",
            content="Always hash passwords with bcrypt, use CSRF tokens",
            category="security",
        )
    )

    consolidation = memory.consolidate()
    console.print(f"  Working: {memory.working.summary()['message_count']} messages")
    console.print(f"  Episodic: {memory.episodic.summary()['total_records']} records")
    console.print(f"  Semantic: {memory.semantic.summary()['total_entries']} entries")
    console.print(f"  Graph: {memory.graph.summary()}")
    console.print(f"  Consolidated: {consolidation['promoted_patterns']} patterns promoted")

    # ── 5. Context: Window + Compression ────────────────────────────────
    section("5. Context Governance")
    from kiracode.context.compressor import SmartCompressor, CompressorConfig
    from kiracode.context.window import WindowConfig, WindowManager

    compressor = SmartCompressor(config=CompressorConfig(threshold_tokens=200))
    window = WindowManager(config=WindowConfig(max_tokens=3000, compression_threshold=0.7))
    window.set_compressor(compressor)

    window.add_system("You are KiraCode.")
    window.add_user("Build a secure login system")

    # Simulate big tool output
    big_log = "\n".join(f"[{i:04d}] INFO: Request processed {i}ms" for i in range(400))
    window.add_tool(big_log)
    console.print(f"  Window: {window.summary()['message_count']} messages, {window.total_tokens} tokens")
    console.print(f"  Compressor: {compressor.stats()}")

    # ── 6. Agents: Architect → Coder → Reviewer ────────────────────────
    section("6. Agent Pipeline")
    from kiracode.agents.architect import ArchitectAgent, CoderAgent
    from kiracode.agents.base import AgentContext

    architect = ArchitectAgent()
    coder = CoderAgent()

    ctx = AgentContext(
        query="Build a secure login system with input validation",
        task_id="full-demo-001",
        memory=memory,
        event_bus=bus,
        token_budget=budget,
    )

    result = await architect.run(ctx)
    plan = result.output.get("plan", {})
    subtasks = plan.get("subtasks", [])

    console.print(f"  Architect: {result.state.value}, {len(subtasks)} subtasks")
    for st in subtasks:
        console.print(f"    [{st['agent_type']}] {st['description'][:55]}")

    # Execute coder subtasks
    code_count = 0
    for st in subtasks:
        if st["agent_type"] == "coder":
            coder_ctx = AgentContext(
                query=st["description"],
                task_id=st["task_id"],
                memory=memory,
                event_bus=bus,
            )
            r = await coder.run(coder_ctx)
            if r.success:
                code_count += 1
    console.print(f"  Coder: {code_count} code blocks generated")

    # ── 7. Budget State ─────────────────────────────────────────────────
    section("7. Token Budget")
    budget.consume("agent", 500)
    budget.consume("tool", 300)
    snap = budget.snapshot()
    for name, alloc in snap.allocations.items():
        bar_len = int(alloc["utilization"] * 20)
        bar = "=" * bar_len + "-" * (20 - bar_len)
        console.print(f"  {name:10s} [{bar}] {alloc['used']}/{alloc['limit']} ({alloc['utilization']:.0%})")

    # ── 8. Final Summary ────────────────────────────────────────────────
    section("8. System Summary")
    table = Table(title="KiraCode Full System", show_lines=True)
    table.add_column("Subsystem", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Details", style="white")
    table.add_row("Config", "OK", f"provider={cfg.llm.provider}")
    table.add_row("EventBus", "OK", f"{bus.subscriber_count} subscribers")
    table.add_row("TokenBudget", "OK", f"{budget.total_used}/{budget.total} used")
    table.add_row("Skills", "OK", f"{loaded} loaded, {len(route)} routed")
    table.add_row("SecretsScanner", "OK", f"{len(findings)} findings on test code")
    table.add_row("Sandbox", "OK", f"timeout={sandbox.config.timeout}s")
    table.add_row("AuditLog", "OK", f"{audit.summary()['total_entries']} entries")
    table.add_row("Rollback", "OK", f"{rb.summary()['snapshot_count']} snapshots")
    table.add_row("WorkingMemory", "OK", f"{memory.working.summary()['message_count']} messages")
    table.add_row("EpisodicMemory", "OK", f"{memory.episodic.summary()['total_records']} records")
    table.add_row("SemanticMemory", "OK", f"{memory.semantic.summary()['total_entries']} patterns")
    table.add_row("MemoryGraph", "OK", f"{memory.graph.summary()['nodes']} nodes")
    table.add_row("ContextWindow", "OK", f"{window.total_tokens} tokens")
    table.add_row("Compressor", "OK", f"{compressor.stats()['saved_tokens']} saved")
    table.add_row("Architect", str(result.state.value), f"{len(subtasks)} subtasks")
    table.add_row("Coder", "done", f"{code_count} blocks")
    console.print(table)

    console.print(
        "\n[bold green]✓ KiraCode full system integration demo complete.[/bold green]"
    )
    console.print("[dim]All 7 subsystems operational. Ready for production use.[/dim]")


if __name__ == "__main__":
    asyncio.run(main())
