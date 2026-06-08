"""Phase 2 Step 4 — Context Governance Integration Demo.

Simulates a realistic coding session with:
  1) Multiple tool calls returning large results
  2) Automatic compression when window budget is exceeded
  3) Reference tracking and on-demand restoration
  4) Token budget monitoring throughout

Run:  python demo_context.py
"""

from __future__ import annotations

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

from kiracode.context.compressor import SmartCompressor, CompressorConfig
from kiracode.context.window import WindowConfig, WindowManager
from kiracode.memory.episodic import TaskRecord
from kiracode.memory.manager import MemoryManager
from kiracode.memory.working import Message, MessageRole
from kiracode.utils.token_counter import count_tokens

console = Console()

# ── helpers ────────────────────────────────────────────────────────────────


def section(title: str) -> None:
    console.print(f"\n[bold cyan]{'=' * 70}[/bold cyan]")
    console.print(f"[bold cyan]  {title}[/bold cyan]")
    console.print(f"[bold cyan]{'=' * 70}[/bold cyan]\n")


def show_window(window: WindowManager, label: str = "Window") -> None:
    s = window.summary()
    table = Table(title=f"{label} State", show_lines=False)
    table.add_column("Metric", style="white")
    table.add_column("Value", style="green")
    for k, v in s.items():
        table.add_row(k, str(v))
    console.print(table)


def show_messages(window: WindowManager) -> None:
    table = Table(title="Messages in Window", show_lines=True)
    table.add_column("#", style="dim")
    table.add_column("Role", style="cyan")
    table.add_column("Tokens", style="yellow", justify="right")
    table.add_column("Compressed", style="magenta")
    table.add_column("Ref ID", style="blue")
    table.add_column("Preview", style="white", max_width=50)
    for i, m in enumerate(window.get_messages()):
        compressed = "YES" if m.metadata.get("compressed") else "-"
        ref_id = m.metadata.get("ref_id", "-")
        preview = m.content[:80].replace("\n", " ")
        table.add_row(str(i), m.role.value, str(m.token_count), compressed, ref_id, preview)
    console.print(table)


# ── mock tool outputs ──────────────────────────────────────────────────────


def generate_mock_log(task_id: str, lines: int = 500) -> str:
    """Generate a realistic-looking server log output."""
    levels = ["INFO", "DEBUG", "WARN", "ERROR"]
    modules = ["auth", "db", "cache", "api", "scheduler", "worker"]
    templates = [
        "[{level}] [{mod}] Request processed in {ms}ms status={code}",
        "[{level}] [{mod}] Connection pool: active={pool_a} idle={pool_i}",
        "[{level}] [{mod}] Cache hit ratio: {ratio}%",
        "[{level}] [{mod}] Query executed: SELECT * FROM users WHERE id={uid}",
        "[ERROR] [{mod}] Connection timeout after {ms}ms to {host}:{port}",
        "[WARN] [{mod}] Slow query detected: {ms}ms threshold=100ms",
        "[{level}] [{mod}] Memory usage: {mem_mb}MB / 2048MB",
        "[{level}] [{mod}] Task {task_id} completed in {ms}ms",
    ]
    import random
    random.seed(42)  # deterministic

    output_lines = [f"=== Server Log for Task {task_id} ===", f"=== {lines} entries ===", ""]
    for i in range(lines):
        level = levels[random.randint(0, 3)]
        mod = modules[random.randint(0, len(modules) - 1)]
        tpl = templates[random.randint(0, len(templates) - 1)]
        line = tpl.format(
            level=level, mod=mod,
            ms=random.randint(1, 500),
            code=random.choice([200, 200, 200, 201, 400, 404, 500]),
            pool_a=random.randint(5, 20), pool_i=random.randint(0, 10),
            ratio=random.randint(60, 99), uid=random.randint(1000, 9999),
            host="db.internal", port=5432, mem_mb=random.randint(200, 1800),
            task_id=task_id,
        )
        output_lines.append(f"[{i:04d}] {line}")
    return "\n".join(output_lines)


def generate_mock_json_result() -> str:
    """Generate a large JSON tool result."""
    data = {
        "status": "success",
        "total_files_scanned": 847,
        "issues": [
            {
                "file": f"src/module_{i}.py",
                "line": 10 + i * 3,
                "severity": ["low", "medium", "high", "critical"][i % 4],
                "message": f"Potential issue found in function handle_{i}",
                "code": f"def handle_{i}(data): return data['key_{i}']",
            }
            for i in range(50)
        ],
        "summary": {
            "critical": 12, "high": 13, "medium": 13, "low": 12,
            "fix_suggestions": [
                "Use parameterized queries to prevent SQL injection",
                "Add input validation for all user-facing endpoints",
                "Implement rate limiting on authentication endpoints",
                "Add CSRF protection to form submissions",
            ],
        },
        "metadata": {
            "scanner_version": "2.1.0",
            "rules_applied": 156,
            "scan_duration_ms": 3420,
            "timestamp": "2026-05-30T10:30:00Z",
        },
    }
    return json.dumps(data, indent=2, ensure_ascii=False)


# ── main demo ──────────────────────────────────────────────────────────────


def main() -> None:
    console.print(
        Panel(
            "[bold]KiraCode — Context Governance Integration Demo[/bold]\n"
            "Demonstrates: sliding window, smart compression, reference tracking\n"
            "across a realistic multi-tool coding session.",
            border_style="bright_blue",
        )
    )

    # Setup: small budget to make demo interesting
    compressor = SmartCompressor(
        config=CompressorConfig(threshold_tokens=300, max_summary_tokens=200)
    )
    window = WindowManager(
        config=WindowConfig(
            max_tokens=3000,
            compression_threshold=0.7,
            min_recent_messages=2,
        )
    )
    window.set_compressor(compressor)
    memory = MemoryManager()

    # ── Step 1: System prompt ────────────────────────────────────────────
    section("Step 1: System Prompt")
    window.add_system(
        "You are KiraCode, an AI coding assistant. You help users write, "
        "review, and debug code. Always explain your reasoning."
    )
    memory.remember_message(
        Message(role=MessageRole.SYSTEM, content="System prompt loaded")
    )
    show_window(window, "After System Prompt")

    # ── Step 2: User query ──────────────────────────────────────────────
    section("Step 2: User Query")
    user_query = "帮我审查项目中的安全漏洞，并生成修复报告"
    window.add_user(user_query)
    memory.remember_message(Message(role=MessageRole.USER, content=user_query))
    console.print(f"[yellow]User:[/yellow] {user_query}")
    show_window(window, "After User Query")

    # ── Step 3: First tool call — small result ──────────────────────────
    section("Step 3: Tool Call — File Listing (small result)")
    small_result = (
        "Found 12 Python files in src/:\n"
        "  src/auth/login.py\n"
        "  src/auth/register.py\n"
        "  src/api/routes.py\n"
        "  src/api/middleware.py\n"
        "  src/db/connection.py\n"
        "  src/db/models.py\n"
        "  src/utils/helpers.py\n"
        "  src/utils/validators.py\n"
        "  src/security/scanner.py\n"
        "  src/security/sandbox.py\n"
        "  src/main.py\n"
        "  src/config.py"
    )
    window.add_tool(small_result)
    console.print(f"Tool result: {count_tokens(small_result)} tokens (below threshold)")
    show_window(window, "After Small Tool Result")

    # ── Step 4: Second tool call — HUGE log output ──────────────────────
    section("Step 4: Tool Call — Server Log Analysis (5000+ tokens)")
    big_log = generate_mock_log("scan-001", lines=500)
    log_tokens = count_tokens(big_log)
    console.print(f"Tool result: {log_tokens} tokens, {len(big_log.splitlines())} lines")
    console.print(f"[dim]First 200 chars: {big_log[:200]}[/dim]")

    window.add_tool(big_log)
    console.print("\n[bold]After compression:[/bold]")
    show_window(window, "After Big Log Compression")
    show_messages(window)

    # ── Step 5: Third tool call — large JSON result ─────────────────────
    section("Step 5: Tool Call — Security Scan Results (large JSON)")
    json_result = generate_mock_json_result()
    json_tokens = count_tokens(json_result)
    console.print(f"Tool result: {json_tokens} tokens")

    window.add_tool(json_result)
    console.print("\n[bold]After compression:[/bold]")
    show_window(window, "After JSON Compression")
    show_messages(window)

    # ── Step 6: Assistant response ──────────────────────────────────────
    section("Step 6: Assistant Response")
    response = (
        "Based on the security scan, I found 847 files with 50 issues:\n"
        "- 12 Critical: SQL injection, missing auth checks\n"
        "- 13 High: XSS vulnerabilities, insecure deserialization\n"
        "- 13 Medium: Weak crypto, missing rate limiting\n"
        "- 12 Low: Information disclosure, verbose errors\n\n"
        "I'll generate a fix for the most critical issues first."
    )
    window.add_assistant(response)
    memory.remember_message(Message(role=MessageRole.ASSISTANT, content=response))
    show_window(window, "After Assistant Response")

    # ── Step 7: Store execution in episodic memory ──────────────────────
    section("Step 7: Episodic Memory — Store Task Record")
    rec = TaskRecord(
        task_id="security-scan-001",
        task_type="security_scan",
        description="Scan project for security vulnerabilities",
        agent_name="security_auditor",
        input_data={"target": "src/", "files_scanned": 847},
        output_data={"issues": 50, "critical": 12, "high": 13},
    )
    rec.mark_success()
    memory.remember_task(rec)
    console.print("Task record stored in episodic memory.")
    console.print_json(json.dumps(memory.episodic.summary(), indent=2))

    # ── Step 8: Reference resolution demo ───────────────────────────────
    section("Step 8: Reference Resolution — Restore Original Content")
    refs_found = 0
    for m in window.get_messages():
        ref_id = m.metadata.get("ref_id")
        if ref_id:
            original = compressor.resolve_reference(ref_id)
            if original:
                refs_found += 1
                orig_tokens = count_tokens(original)
                console.print(f"\n[bold]Resolving ref: {ref_id}[/bold]")
                console.print(f"  Compressed: {m.token_count} tokens")
                console.print(f"  Original:   {orig_tokens} tokens")
                console.print(f"  Savings:    {orig_tokens - m.token_count} tokens ({(1 - m.token_count/orig_tokens)*100:.1f}%)")
                console.print(f"  First 150 chars: [dim]{original[:150]}[/dim]")
    if refs_found == 0:
        console.print("[yellow]No compressed references found.[/yellow]")

    # ── Step 9: Final state ─────────────────────────────────────────────
    section("Step 9: Final State Summary")

    # Window summary
    console.print("[bold]Context Window:[/bold]")
    show_window(window, "Final Window")

    # Compressor stats
    console.print("\n[bold]Compressor Stats:[/bold]")
    console.print_json(json.dumps(compressor.stats(), indent=2))

    # Memory summary
    console.print("\n[bold]Memory System:[/bold]")
    console.print_json(json.dumps(memory.full_summary(), indent=2))

    # Overall token savings
    total_original = sum(
        m.metadata.get("original_tokens", m.token_count)
        for m in window.get_messages()
    )
    total_compressed = window.total_tokens
    console.print(f"\n[bold green]Token Budget Report:[/bold green]")
    console.print(f"  Without compression: {total_original} tokens")
    console.print(f"  With compression:    {total_compressed} tokens")
    console.print(f"  Saved:               {total_original - total_compressed} tokens ({(1 - total_compressed/total_original)*100:.1f}%)")

    console.print(
        "\n[bold green]✓ Integration demo complete. "
        "Context governance fully operational.[/bold green]"
    )


if __name__ == "__main__":
    main()
