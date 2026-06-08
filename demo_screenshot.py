"""KiraCode — Screenshot Analysis Demo.

Demonstrates the multimodal vision pipeline:
  UI Screenshot → OpenCV Preprocessing → Qwen-VL Analysis → Structured Description

Usage:
  # With a local screenshot file:
  python demo_screenshot.py --image path/to/screenshot.png

  # With a sample image (auto-generated):
  python demo_screenshot.py --demo

  # With custom instruction:
  python demo_screenshot.py --image screenshot.png --instruction "用 React + Tailwind 实现"

Prerequisites:
  export DASHSCOPE_API_KEY=sk-xxxx   # 阿里云百炼 API Key
  pip install opencv-python-headless  # For preprocessing
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

import click
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

console = Console()


def section(title: str) -> None:
    console.print(f"\n[bold bright_cyan]{'='*60}[/bold bright_cyan]")
    console.print(f"[bold bright_cyan]  {title}[/bold bright_cyan]")
    console.print(f"[bold bright_cyan]{'='*60}[/bold bright_cyan]\n")


def _generate_sample_png() -> bytes:
    """Generate a minimal valid PNG for demo purposes (no OpenCV dependency)."""
    # 1x1 white PNG
    import base64
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4DwAAAQEABRjYTgAAAABJRU5ErkJggg=="
    )


async def run_demo(image_input: str, instruction: str, detail_level: str) -> None:
    """Run the full screenshot analysis demo."""
    from kiracode.skills.builtin.screenshot_analyze import SkillClass
    from kiracode.skills.loader import SkillLoader
    from kiracode.skills.registry import registry

    section("Step 1: Load Skill")
    loader = SkillLoader(registry)
    loaded = loader.load_from_directory("kiracode/skills/builtin")
    console.print(f"Loaded [green]{loaded}[/green] builtin skills")

    skill_meta = registry.get("screenshot_analyze")
    if skill_meta:
        console.print(f"  Skill: [cyan]{skill_meta.name}[/cyan]")
        console.print(f"  Tags: {skill_meta.tags}")
        console.print(f"  Capabilities: {skill_meta.capabilities}")

    section("Step 2: Image Input")
    console.print(f"Input: [yellow]{image_input[:80]}[/yellow]")
    console.print(f"Detail level: [yellow]{detail_level}[/yellow]")
    console.print(f"Instruction: [yellow]{instruction}[/yellow]")

    if not os.environ.get("DASHSCOPE_API_KEY"):
        console.print("\n[bold red]ERROR:[/bold red] DASHSCOPE_API_KEY not set.")
        console.print("Run: [cyan]export DASHSCOPE_API_KEY=sk-your-key[/cyan]")
        console.print("\n[dim]Showing mock result for demo purposes...[/dim]\n")
        _show_mock_result()
        return

    section("Step 3: Screenshot Analysis (Qwen-VL)")
    skill = SkillClass()

    with console.status("[bold green]Analyzing screenshot..."):
        result = await skill.execute(
            image_input=image_input,
            detail_level=detail_level,
        )

    if not result.get("success"):
        console.print(f"[red]Error:[/red] {result.get('error')}")
        return

    section("Step 4: Analysis Result")

    # Display components
    components = result.get("components", [])
    if components:
        comp_table = Table(title="Detected Components", show_lines=True)
        comp_table.add_column("#", style="dim")
        comp_table.add_column("Type", style="cyan")
        comp_table.add_column("Text", style="white")
        comp_table.add_column("Position", style="yellow")
        comp_table.add_column("Color", style="magenta")

        for i, c in enumerate(components[:15]):
            pos = c.get("position", {})
            pos_str = f"({pos.get('x',0)},{pos.get('y',0)}) {pos.get('width',0)}x{pos.get('height',0)}"
            color = c.get("color", {})
            color_str = color.get("bg", "-") if isinstance(color, dict) else str(color)
            comp_table.add_row(
                str(i + 1),
                c.get("type", "?"),
                (c.get("text", "") or "")[:30],
                pos_str,
                color_str,
            )
        console.print(comp_table)

    # Display layout
    layout = result.get("layout", {})
    if layout:
        console.print(f"\n[bold]Layout:[/bold] {layout.get('type', '?')} — {layout.get('description', '')}")

    # Display colors
    colors = result.get("colors", {})
    if colors:
        console.print(f"\n[bold]Colors:[/bold]")
        for key in ["primary", "secondary", "background", "accent"]:
            val = colors.get(key)
            if val:
                console.print(f"  {key}: [on {val}]  [/on {val}] {val}")

    # Display tech recommendations
    tech = result.get("tech_recommendations", {})
    if tech:
        console.print(f"\n[bold]Tech Recommendations:[/bold]")
        console.print(f"  Framework: [cyan]{tech.get('framework', '?')}[/cyan]")
        console.print(f"  Styling: [cyan]{tech.get('styling', '?')}[/cyan]")
        console.print(f"  Layout: [cyan]{tech.get('layout_strategy', '?')}[/cyan]")

    # Full JSON
    section("Step 5: Full JSON Output")
    json_str = json.dumps(result, ensure_ascii=False, indent=2)
    console.print(Syntax(json_str, "json", theme="monokai", word_wrap=True))

    section("Step 6: Integration with Agent")
    console.print("The structured analysis is injected into the Agent pipeline as:")
    console.print("  1. [cyan]System memory message[/cyan] — available to ArchitectAgent for planning")
    console.print("  2. [cyan]Context metadata[/cyan] — passed to CoderAgent for code generation")
    console.print("  3. [cyan]Skill Router match[/cyan] — auto-triggered by vision keywords\n")
    console.print("[dim]In the full pipeline, the ArchitectAgent would decompose this into:")
    console.print("  SubTask 1: Generate HTML structure from components list")
    console.print("  SubTask 2: Apply CSS/Tailwind styles from colors + typography")
    console.print("  SubTask 3: Implement layout using detected grid/flex patterns[/dim]")


def _show_mock_result() -> None:
    """Show a mock analysis result for demo without API key."""
    mock = {
        "success": True,
        "cached": False,
        "model": "qwen-vl-max",
        "components": [
            {"type": "navbar", "text": "Logo  Home  About  Contact", "position": {"x": 0, "y": 0, "width": 1200, "height": 60}, "color": {"bg": "#ffffff", "text": "#333333"}},
            {"type": "header", "text": "Welcome to Our Platform", "position": {"x": 100, "y": 120, "width": 1000, "height": 80}, "color": {"bg": "#f8f9fa", "text": "#212529"}},
            {"type": "card", "text": "Feature 1 - Fast and Reliable", "position": {"x": 100, "y": 280, "width": 300, "height": 200}, "color": {"bg": "#ffffff", "text": "#333333"}},
            {"type": "card", "text": "Feature 2 - Easy to Use", "position": {"x": 450, "y": 280, "width": 300, "height": 200}, "color": {"bg": "#ffffff", "text": "#333333"}},
            {"type": "card", "text": "Feature 3 - Scalable", "position": {"x": 800, "y": 280, "width": 300, "height": 200}, "color": {"bg": "#ffffff", "text": "#333333"}},
            {"type": "button", "text": "Get Started", "position": {"x": 500, "y": 550, "width": 200, "height": 50}, "color": {"bg": "#007bff", "text": "#ffffff"}},
            {"type": "footer", "text": "2026 Company Name. All rights reserved.", "position": {"x": 0, "y": 700, "width": 1200, "height": 80}, "color": {"bg": "#343a40", "text": "#ffffff"}},
        ],
        "layout": {"type": "flex", "direction": "vertical", "description": "Top navbar, hero section with heading, 3-column feature cards, CTA button, footer", "sections": ["navbar", "header", "main", "footer"]},
        "colors": {"primary": "#007bff", "secondary": "#6c757d", "background": "#ffffff", "surface": "#f8f9fa", "text_primary": "#212529", "accent": "#28a745", "palette": ["#007bff", "#ffffff", "#333333", "#f8f9fa", "#343a40"]},
        "typography": {"font_family": "system-ui, sans-serif", "heading_style": "bold, 32px", "body_style": "regular, 16px"},
        "style_suggestions": "Use Flexbox for the 3-column card layout. Navbar uses flex justify-between. Cards have shadow-sm and rounded-lg. CTA button is primary color with hover effect.",
        "tech_recommendations": {"framework": "react", "styling": "tailwind", "layout_strategy": "flexbox"},
    }

    table = Table(title="Mock Analysis Result — Components", show_lines=True)
    table.add_column("Type", style="cyan")
    table.add_column("Text", style="white")
    table.add_column("Position", style="yellow")

    for c in mock["components"]:
        pos = c["position"]
        table.add_row(c["type"], c["text"][:40], f"({pos['x']},{pos['y']}) {pos['width']}x{pos['height']}")
    console.print(table)

    console.print(f"\n[bold]Layout:[/bold] {mock['layout']['description']}")
    console.print(f"[bold]Framework:[/bold] {mock['tech_recommendations']['framework']}")
    console.print(f"[bold]Styling:[/bold] {mock['tech_recommendations']['styling']}")


@click.command()
@click.option("--image", "-i", default=None, help="Path to UI screenshot image")
@click.option("--instruction", "-t", default="用 React + Tailwind 实现这个界面", help="Text instruction")
@click.option("--detail", "-d", default="standard", type=click.Choice(["fast", "standard", "detailed"]), help="Analysis detail level")
@click.option("--demo", is_flag=True, help="Run with mock data (no API key needed)")
def main(image: str | None, instruction: str, detail: str, demo: bool) -> None:
    """KiraCode Screenshot Analysis Demo — multimodal UI understanding."""
    console.print(Panel(
        "[bold bright_cyan]KiraCode Screenshot Analysis Demo[/bold bright_cyan]\n"
        "Multimodal vision pipeline: Screenshot → OpenCV → Qwen-VL → Structured Description",
        border_style="bright_blue",
    ))

    if demo:
        console.print("[dim]Running in demo mode with mock data...[/dim]\n")
        _show_mock_result()
        return

    if not image:
        console.print("[red]Please provide --image path or use --demo[/red]")
        return

    asyncio.run(run_demo(image, instruction, detail))


if __name__ == "__main__":
    main()
