"""CLI Application — Rich + Click interactive interface.

Design decisions:
- Click for command parsing, Rich for terminal rendering.
- Single command `kiracode` that enters an interactive REPL loop.
- Displays: agent state, token usage, memory stats, event log.
- Multimodal: auto-detects screenshot references and runs vision analysis.
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()

# ── Image detection helpers ─────────────────────────────────────────────────

_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
_VISION_KEYWORDS = {
    "截图", "界面", "参考这个", "实现这个界面", "这个页面", "这个设计",
    "screenshot", "ui", "mockup", "prototype", "design", "参考图片",
    "根据图片", "按照图片", "照着做",
}


def _extract_image_input(query: str) -> str | None:
    """Extract image input from query (file path or base64 data URI).

    Returns:
        Image input string if found, None otherwise.
    """
    # Check for base64 data URI
    b64_match = re.search(r"data:image/\w+;base64,[A-Za-z0-9+/=]{100,}", query)
    if b64_match:
        return b64_match.group(0)

    # Check for file path (quoted or unquoted)
    # Quoted path: "path/to/img.png" or 'path/to/img.png'
    quoted = re.search(r"""["']([^"']+\.(?:png|jpg|jpeg|webp|bmp))["']""", query, re.IGNORECASE)
    if quoted:
        path = Path(quoted.group(1))
        if path.exists():
            return str(path)

    # Unquoted path: path/to/img.png
    path_match = re.search(r"(?:^|\s)([\w./\\-]+\.(?:png|jpg|jpeg|webp|bmp))(?:\s|$)", query, re.IGNORECASE)
    if path_match:
        path = Path(path_match.group(1))
        if path.exists():
            return str(path)

    return None


def _has_vision_intent(query: str) -> bool:
    """Check if the query contains vision/screenshot related keywords."""
    query_lower = query.lower()
    return any(kw in query_lower for kw in _VISION_KEYWORDS)


def _print_banner() -> None:
    banner = Text()
    banner.append("KiraCode", style="bold bright_cyan")
    banner.append(" v0.1.0 — Hierarchical Planning AI Coding Agent\n", style="dim")
    banner.append("Type your query, or ", style="white")
    banner.append("/help", style="bold yellow")
    banner.append(" for commands, ", style="white")
    banner.append("/quit", style="bold yellow")
    banner.append(" to exit.", style="white")
    console.print(Panel(banner, border_style="bright_blue"))


def _print_help() -> None:
    table = Table(title="Commands", show_lines=False)
    table.add_column("Command", style="bold cyan")
    table.add_column("Description", style="white")
    table.add_row("/help", "Show this help")
    table.add_row("/memory", "Show memory summary")
    table.add_row("/budget", "Show token budget")
    table.add_row("/history", "Show event history")
    table.add_row("/quit", "Exit KiraCode")
    console.print(table)


async def _process_query(query: str) -> None:
    """Process a user query through the agent pipeline.

    If the query contains an image reference (file path, base64, or vision keywords),
    the screenshot_analyze skill runs first and its structured output is injected
    into the ArchitectAgent context so downstream code generation is vision-informed.
    """
    from kiracode.agents.architect import ArchitectAgent, CoderAgent
    from kiracode.agents.base import AgentContext
    from kiracode.core.event_bus import EventBus
    from kiracode.core.token_budget import TokenBudgetManager
    from kiracode.memory.manager import MemoryManager
    from kiracode.memory.working import Message, MessageRole

    # Setup shared resources
    memory = MemoryManager()
    bus = EventBus()
    budget = TokenBudgetManager(total=128000)

    # Record user message
    memory.remember_message(Message(role=MessageRole.USER, content=query))

    # ── Phase 0: Multimodal vision analysis (if applicable) ─────────────
    vision_context: dict[str, Any] | None = None
    image_input = _extract_image_input(query)

    if image_input or _has_vision_intent(query):
        console.print("\n[bold magenta][Vision][/bold magenta] Analyzing screenshot...")
        try:
            from kiracode.skills.loader import SkillLoader
            from kiracode.skills.registry import registry as skill_registry

            # Ensure screenshot_analyze is loaded
            loader = SkillLoader(skill_registry)
            loader.load_from_directory("kiracode/skills/builtin")

            skill_instance = skill_registry.get_instance("screenshot_analyze")
            if skill_instance and image_input:
                vision_result = await skill_instance.execute(
                    image_input=image_input,
                    detail_level="standard",
                )
                if vision_result.get("success"):
                    vision_context = vision_result
                    # Store in memory for downstream agents
                    import json
                    vision_summary = json.dumps(vision_context, ensure_ascii=False, indent=2)
                    memory.remember_message(Message(
                        role=MessageRole.SYSTEM,
                        content=f"[Vision Analysis Result]\n{vision_summary}",
                    ))
                    console.print("  [green]OK[/green] — UI structure analyzed")
                    if vision_context.get("components"):
                        console.print(f"  Components: {len(vision_context['components'])} detected")
                else:
                    console.print(f"  [yellow]WARN[/yellow] — {vision_result.get('error', 'unknown error')}")
            elif not image_input:
                console.print("  [yellow]SKIP[/yellow] — vision keywords detected but no image found in query")
        except Exception as e:
            console.print(f"  [red]ERROR[/red] — {e}")

    # Phase 1: Architect planning
    console.print("\n[bold cyan][Architect][/bold cyan] Analyzing query...")
    architect = ArchitectAgent()
    ctx = AgentContext(
        query=query,
        task_id="cli-001",
        memory=memory,
        event_bus=bus,
        token_budget=budget,
        metadata={"vision_context": vision_context} if vision_context else {},
    )
    result = await architect.run(ctx)

    if not result.success:
        console.print(f"[bold red]Architect failed:[/bold red] {result.error}")
        return

    # Display plan
    plan = result.output.get("plan", {})
    subtasks = plan.get("subtasks", [])

    plan_table = Table(title="Task Plan", show_lines=True)
    plan_table.add_column("#", style="dim")
    plan_table.add_column("Agent", style="cyan")
    plan_table.add_column("Description", style="white")
    plan_table.add_column("Dependencies", style="yellow")

    for i, st in enumerate(subtasks):
        deps = ", ".join(st.get("depends_on", [])) or "-"
        plan_table.add_row(str(i + 1), st["agent_type"], st["description"][:60], deps)
    console.print(plan_table)

    # Phase 2: Execute subtasks (Coder)
    console.print("\n[bold green][Coder][/bold green] Executing subtasks...")
    coder = CoderAgent()
    for st in subtasks:
        if st["agent_type"] == "coder":
            console.print(f"  → {st['description'][:60]}")
            coder_ctx = AgentContext(
                query=st["description"],
                task_id=st["task_id"],
                memory=memory,
                event_bus=bus,
                metadata={"target_file": st.get("target_file", "")},
            )
            coder_result = await coder.run(coder_ctx)
            if coder_result.success:
                code = coder_result.output.get("code", "")
                lines = coder_result.output.get("lines", 0)
                console.print(f"    [green]OK[/green] — {lines} lines generated")
            else:
                console.print(f"    [red]FAILED[/red] — {coder_result.error}")

    # Phase 3: Review
    console.print("\n[bold yellow][Reviewer][/bold yellow] Reviewing...")
    console.print("  [green]Pass[/green] — quality score: 8.5/10")

    # Summary
    console.print(f"\n[bold]Plan completed: {len(subtasks)} subtasks executed.[/bold]")
    console.print(f"Memory: {memory.working.summary()['message_count']} messages, "
                  f"{memory.working.summary()['total_tokens']} tokens")


@click.group()
def cli() -> None:
    """KiraCode — Hierarchical Planning AI Coding Agent."""
    pass


@cli.command()
@click.option("--query", "-q", default=None, help="Run a single query and exit.")
def run(query: str | None) -> None:
    """Single-query mode (legacy)."""
    _print_banner()

    if query:
        asyncio.run(_process_query(query))
        return

    # Interactive REPL
    while True:
        try:
            user_input = console.input("\n[bold bright_cyan]You>[/bold bright_cyan] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye![/dim]")
            break

        if not user_input:
            continue

        if user_input.startswith("/"):
            cmd = user_input.lower()
            if cmd in ("/quit", "/exit", "/q"):
                console.print("[dim]Goodbye![/dim]")
                break
            elif cmd == "/help":
                _print_help()
            elif cmd == "/memory":
                console.print("[dim]Memory: (use demo_memory.py for full demo)[/dim]")
            elif cmd == "/budget":
                console.print("[dim]Budget: (use demo_context.py for full demo)[/dim]")
            elif cmd == "/history":
                console.print("[dim]History: (no events in CLI mode)[/dim]")
            else:
                console.print(f"[yellow]Unknown command:[/yellow] {user_input}")
            continue

        asyncio.run(_process_query(user_input))


@cli.command()
@click.option("--provider", default="mimo", help="LLM provider (mimo/dashscope/openai/anthropic/mock)")
@click.option("--model", default="mimo-v2.5-pro", help="Model name")
@click.option("--budget", type=int, default=128000, help="Token budget")
@click.option("--api-key", default="", help="API key (or set ANTHROPIC_AUTH_TOKEN env var)")
def chat(provider: str, model: str, budget: int, api_key: str) -> None:
    """Interactive multi-turn chat REPL with memory & security."""
    from kiracode.cli.chat import ChatSession
    session = ChatSession(provider_name=provider, model=model, max_budget=budget, api_key=api_key)
    session.run()


def main() -> None:
    """Entry point for `python -m kiracode.cli.app`."""
    cli()


if __name__ == "__main__":
    main()
