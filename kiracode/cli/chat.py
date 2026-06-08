"""Interactive Multi-Turn Chat REPL — KiraCode + MiMo.

Commands:
  /help         Show all commands
  /memory       Display 3-layer memory status
  /budget       Token budget dashboard
  /security     SAST scan on code blocks in session
  /audit        View session audit log
  /consolidate  Trigger memory consolidation
  /save [file]  Export session as Markdown
  /clear        Clear messages (keep memory)
  /quit         Exit
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from kiracode.llm.base import LLMMessage, LLMResponse, MessageRole

console = Console()


# ── Welcome Banner ──────────────────────────────────────────────────────────

WELCOME_ART = r"""
[bold bright_cyan]
 ██╗  ██╗██╗██████╗  █████╗
 ██║ ██╔╝██║██╔══██╗██╔══██╗
 █████╔╝ ██║██████╔╝███████║
 ██╔═██╗ ██║██╔══██╗██╔══██║
 ██║  ██╗██║██║  ██║██║  ██║
 ╚═╝  ╚═╝╚═╝╚═╝  ╚═╝╚═╝  ╚═╝
[/bold bright_cyan]
[dim]Interactive Chat — Multi-turn with Memory & Security[/dim]
"""


# ── ChatSession ─────────────────────────────────────────────────────────────


class ChatSession:
    """Manages a multi-turn chat session with MiMo + KiraCode subsystems."""

    def __init__(
        self,
        provider_name: str = "mimo",
        model: str = "mimo-v2.5-pro",
        max_budget: int = 128000,
        api_key: str = "",
    ) -> None:
        self.session_id = str(uuid.uuid4())[:8]
        self.messages: list[LLMMessage] = []
        self.round_count: int = 0
        self.total_prompt_tokens: int = 0
        self.total_completion_tokens: int = 0

        # LLM Provider
        import os
        from kiracode.llm.factory import create_provider
        resolved_key = api_key or os.environ.get("ANTHROPIC_AUTH_TOKEN", "") or os.environ.get("MIMO_API_KEY", "") or os.environ.get("DASHSCOPE_API_KEY", "")
        self.provider = create_provider(
            provider_name,
            model=model,
            api_key=resolved_key if resolved_key else None,
        )

        # Memory
        from kiracode.memory.manager import MemoryManager
        self.memory = MemoryManager()

        # Token Budget
        from kiracode.core.token_budget import TokenBudgetManager
        self.budget = TokenBudgetManager(total=max_budget)

        # Security scanners
        from kiracode.security.bandit_adapter import BanditRuleAdapter
        from kiracode.security.semgrep_adapter import SemgrepRuleAdapter
        from kiracode.security.audit_log import AuditLog
        self.bandit = BanditRuleAdapter()
        self.semgrep = SemgrepRuleAdapter()
        self.audit = AuditLog()

    # ── Main Loop ───────────────────────────────────────────────────────

    def run(self) -> None:
        """Start the interactive REPL."""
        self._show_welcome()

        while True:
            try:
                user_input = console.input(
                    "\n[bold green]You[/bold green] "
                ).strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]Goodbye![/dim]")
                break

            if not user_input:
                continue

            if user_input.startswith("/"):
                if self._handle_command(user_input):
                    break  # /quit returns True
                continue

            # Normal chat turn — close httpx client after each turn
            # because asyncio.run() creates/destroys event loops per call,
            # and httpx connections are bound to the loop they were created on.
            try:
                asyncio.run(self._run_turn_and_cleanup(user_input))
            except Exception as e:
                console.print(f"[bold red][错误][/bold red] 发生异常，程序将继续运行: {e}")

    # ── Welcome ─────────────────────────────────────────────────────────

    def _show_welcome(self) -> None:
        console.print(WELCOME_ART)
        info = Table(show_header=False, box=None, padding=(0, 2))
        info.add_column("Key", style="dim")
        info.add_column("Value", style="bold")
        info.add_row("Session", self.session_id)
        info.add_row("Provider", self.provider.provider_name)
        info.add_row("Model", self.provider.model)
        info.add_row("Budget", f"{self.budget.total:,} tokens")
        info.add_row("Commands", "/help for all commands")
        console.print(Panel(info, border_style="bright_blue", title="Config"))

    # ── Chat Turn ───────────────────────────────────────────────────────

    async def _run_turn_and_cleanup(self, user_input: str) -> None:
        """Run a chat turn and ensure httpx client is closed afterward."""
        try:
            await self._chat_turn(user_input)
        except Exception as e:
            console.print(f"[bold red][错误][/bold red] 调用 LLM 失败，请检查网络或 API Key: {e}")
        finally:
            close = getattr(self.provider, "close", None)
            if close:
                await close()

    # ── Tool definitions (OpenAI function-calling format) ───────────────

    TOOLS = [
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "Write content to a file at the given path. Creates parent directories if needed.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Absolute or relative file path"},
                        "content": {"type": "string", "description": "Content to write to the file"},
                    },
                    "required": ["path", "content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read the content of a file at the given path.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Absolute or relative file path"},
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_command",
                "description": "Execute a shell command and return its output.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Shell command to execute"},
                    },
                    "required": ["command"],
                },
            },
        },
    ]

    async def _execute_tool(self, name: str, arguments: str) -> str:
        """Execute a tool call and return the result as a string."""
        import json
        from kiracode.skills.loader import SkillLoader
        from kiracode.skills.registry import registry as skill_registry

        # Ensure skills are loaded
        loader = SkillLoader(skill_registry)
        loader.load_from_directory("kiracode/skills/builtin")

        args = json.loads(arguments)

        if name == "write_file":
            skill = skill_registry.get_instance("file_ops")
            result = await skill.execute(action="write", path=args["path"], content=args["content"])
            return json.dumps(result, ensure_ascii=False)

        elif name == "read_file":
            skill = skill_registry.get_instance("file_ops")
            result = await skill.execute(action="read", path=args["path"])
            return json.dumps(result, ensure_ascii=False)

        elif name == "run_command":
            skill = skill_registry.get_instance("shell_exec")
            cmd = args["command"]
            # Use longer timeout for build commands
            timeout = 300
            if any(kw in cmd for kw in ("mvn", "gradle", "npm install", "pip install", "cargo build")):
                timeout = 600
            result = await skill.execute(command=cmd, timeout=timeout)
            return json.dumps(result, ensure_ascii=False)

        else:
            return json.dumps({"success": False, "error": f"Unknown tool: {name}"})

    # ── Chat Turn (with tool-calling loop) ──────────────────────────────

    MAX_TOOL_ROUNDS = 30  # prevent infinite tool-calling loops

    async def _chat_turn(self, user_input: str) -> None:
        """Execute one chat turn with automatic tool-calling loop.

        Flow:
          1. User message → LLM (with tools)
          2. If LLM returns tool_calls → execute each → feed results back
          3. Repeat until LLM returns text (no more tool_calls)
          4. Display final response
        """
        self.round_count += 1

        # 1. Add user message to history
        user_msg = LLMMessage(role=MessageRole.USER, content=user_input)
        self.messages.append(user_msg)

        # 2. Recall relevant memories
        memory_context = ""
        for mem_type in ("semantic", "episodic"):
            try:
                entries = self.memory.recall(user_input, mem_type, top_k=2)
                for entry in entries:
                    desc = getattr(entry, "description", str(entry))
                    memory_context += f"- {mem_type}: {desc}\n"
            except Exception:
                pass

        # 3. Tool-calling loop
        total_prompt = 0
        total_completion = 0
        final_content = ""

        for round_idx in range(self.MAX_TOOL_ROUNDS + 1):
            messages = self._build_messages(memory_context)

            try:
                with console.status("[dim]Thinking...[/dim]"):
                    response = await self.provider.chat(messages, tools=self.TOOLS)
            except Exception as e:
                console.print(f"[bold red][错误][/bold red] 调用 LLM 失败，请检查网络或 API Key: {e}")
                break

            total_prompt += response.usage.get("prompt_tokens", 0)
            total_completion += response.usage.get("completion_tokens", 0)

            # Show thinking/reasoning if present
            if response.reasoning_content:
                thinking = response.reasoning_content[:500]
                console.print(f"  [dim italic]Thinking: {thinking}[/dim italic]")

            # Show partial text if LLM included it with tool calls
            if response.tool_calls and response.content:
                console.print(f"  [dim]{response.content[:200]}[/dim]")

            # No tool calls → final text response
            if not response.tool_calls:
                final_content = response.content
                # Store assistant message
                assistant_msg = LLMMessage(
                    role=MessageRole.ASSISTANT,
                    content=response.content,
                    reasoning_content=response.reasoning_content,
                )
                self.messages.append(assistant_msg)
                break

            # Has tool calls → execute them
            # Store assistant message with tool_calls metadata
            assistant_msg = LLMMessage(
                role=MessageRole.ASSISTANT,
                content=response.content or "",
                metadata={"tool_calls": response.tool_calls},
            )
            self.messages.append(assistant_msg)

            for tc in response.tool_calls:
                func = tc.get("function", {})
                tool_name = func.get("name", "")
                tool_args = func.get("arguments", "{}")
                tool_id = tc.get("id", "")

                console.print(f"  [cyan]Calling tool:[/cyan] {tool_name}")
                try:
                    result = await self._execute_tool(tool_name, tool_args)
                except Exception as e:
                    result = json.dumps({"success": False, "error": str(e)})

                # Show brief result
                try:
                    result_data = json.loads(result)
                    if result_data.get("success"):
                        if tool_name == "write_file":
                            console.print(f"  [green]OK[/green] — {result_data.get('bytes_written', '?')} bytes written")
                        elif tool_name == "read_file":
                            console.print(f"  [green]OK[/green] — {result_data.get('lines', '?')} lines")
                        else:
                            console.print(f"  [green]OK[/green] — exit code 0")
                    else:
                        err = result_data.get("error", "")
                        stderr = result_data.get("stderr", "")
                        exit_code = result_data.get("exit_code", "?")
                        detail = stderr[:200] if stderr else err[:200]
                        console.print(f"  [red]Error[/red] (exit {exit_code}): {detail}")
                except Exception:
                    console.print(f"  [dim]Result:[/dim] {result[:200]}")

                # Append tool result message
                tool_msg = LLMMessage(
                    role=MessageRole.TOOL,
                    content=result,
                    tool_call_id=tool_id,
                    name=tool_name,
                )
                self.messages.append(tool_msg)

        # 4. If tool loop exhausted without final text, force a summary call
        if not final_content:
            try:
                console.print("[dim]Summarizing results...[/dim]")
                messages = self._build_messages(memory_context)
                # Add a user message asking for summary
                messages.append(LLMMessage(role=MessageRole.USER, content="Please summarize what you just did, whether it succeeded or failed, and what the user should do next. Be concise."))
                response = await self.provider.chat(messages)
                final_content = response.content
                total_prompt += response.usage.get("prompt_tokens", 0)
                total_completion += response.usage.get("completion_tokens", 0)
                assistant_msg = LLMMessage(
                    role=MessageRole.ASSISTANT,
                    content=response.content,
                    reasoning_content=response.reasoning_content,
                )
                self.messages.append(assistant_msg)
            except Exception as e:
                console.print(f"[bold red][错误][/bold red] 获取总结失败: {e}")

        # 5. Render final response
        if final_content:
            self._render_response(final_content)
        else:
            console.print("[yellow]任务完成，但未生成总结。请检查上方的工具执行结果。[/yellow]")

        # 6. Update token tracking
        self.total_prompt_tokens += total_prompt
        self.total_completion_tokens += total_completion
        self.budget.consume("agent", total_prompt + total_completion)

        # 6. Record in memory
        from kiracode.memory.working import Message as MemMessage, MessageRole as MemRole
        role_map = {
            MessageRole.USER: MemRole.USER,
            MessageRole.ASSISTANT: MemRole.ASSISTANT,
            MessageRole.SYSTEM: MemRole.SYSTEM,
        }
        self.memory.remember_message(MemMessage(
            role=role_map[user_msg.role],
            content=user_msg.content,
            token_count=total_prompt,
        ))
        if final_content:
            self.memory.remember_message(MemMessage(
                role=MemRole.ASSISTANT,
                content=final_content,
                token_count=total_completion,
            ))

        # 7. Log audit
        from kiracode.security.audit_log import AuditEntry
        await self.audit.log(AuditEntry(
            event_type="chat_turn",
            actor="user",
            action="llm_call",
            details={
                "round": self.round_count,
                "tokens": {"prompt": total_prompt, "completion": total_completion},
                "tool_rounds": min(round_idx + 1, self.MAX_TOOL_ROUNDS),
            },
        ))

        # 8. Show token bar
        self._show_token_bar({"prompt_tokens": total_prompt, "completion_tokens": total_completion})

    def _build_messages(self, memory_context: str = "") -> list[LLMMessage]:
        """Build message list: system (with memory) + history."""
        system_content = r"""You are KiraCode, an autonomous AI coding agent with deep reasoning ability.

## Your Tools
- write_file(path, content) — Create or overwrite a file. Path MUST be absolute or relative to D:\agent\agent-project-codex-7
- read_file(path) — Read a file's content
- run_command(command) — Execute a shell command (runs in D:\agent\agent-project-codex-7)

## CRITICAL: Working Directory
ALL file paths must be under D:\agent\agent-project-codex-7\tests\project\
NEVER write files outside this directory. Use paths like:
  D:/agent/agent-project-codex-7/tests/project/springboot-demo/pom.xml

## Thinking Process
Before each action, think step by step:
1. What is the user asking for?
2. What files need to be created?
3. What is the correct order? (dependencies first)
4. After creating files, what build/run commands are needed?
5. If something fails, what could be wrong and how to fix it?

## Core Rules
1. **Always use tools** — never just describe code. Use write_file to create files, run_command to build and run.
2. **Write COMPLETE code** — no placeholders, no "TODO", no "...", no "// implement later". Every file must be fully functional and runnable.
3. **Be thorough** — include ALL imports, ALL annotations, ALL configurations. A Spring Boot project needs: pom.xml, Application class, Controller, templates, static files, application.properties.
4. **Verify your work** — after creating files, run build commands and check for errors.
5. **Self-heal on errors** — if a build or command fails:
   a. Read the error message carefully
   b. Use read_file to check the problematic file
   c. Fix the code with write_file
   d. Re-run the command
   e. Repeat until it works (up to 5 retries per error)
6. **Continue after success** — after a project builds and runs, report what you did and ask if the user wants anything else.

## When building a Spring Boot project:
1. First create the directory: run_command("mkdir -p D:/agent/agent-project-codex-7/tests/project/PROJECT_NAME")
2. Create pom.xml with spring-boot-starter-web, spring-boot-starter-thymeleaf, spring-boot-maven-plugin
3. Create src/main/java/.../Application.java with @SpringBootApplication
4. Create src/main/java/.../controller/HelloController.java with @RestController + @GetMapping
5. Create src/main/resources/application.properties (server.port=8080)
6. Create src/main/resources/templates/index.html (Thymeleaf template)
7. Create src/main/resources/static/css/style.css and static/js/app.js
8. Build: run_command("cd /d D:/agent/agent-project-codex-7/tests/project/PROJECT_NAME && mvn.cmd clean package -DskipTests")
9. If build fails → read error → fix → rebuild (repeat up to 5 times)
10. Create a start.bat to run in background:
    write_file("D:/agent/agent-project-codex-7/tests/project/PROJECT_NAME/start.bat",
      '@echo off\r\ncd /d %~dp0\r\nstart "" java -jar target\\PROJECT-0.0.1-SNAPSHOT.jar > app.log 2>&1\r\nexit')
    Then run: run_command("cmd.exe /c D:/agent/agent-project-codex-7/tests/project/PROJECT_NAME/start.bat")
    This returns immediately because start.bat calls start and exits.
    Wait 5s for startup: run_command("ping -n 6 127.0.0.1 >nul")
    Check logs: run_command("type D:\\agent\\agent-project-codex-7\\tests\\project\\PROJECT_NAME\\app.log")
    Test: run_command("curl -s http://localhost:8080/")

## Spring Boot specific:
- Use @RestController for API endpoints, @Controller for pages
- Use @GetMapping, @PostMapping etc. with explicit paths
- Return JSON from API endpoints, HTML from page controllers
- Place templates in src/main/resources/templates/ (Thymeleaf)
- Place static files in src/main/resources/static/
- Use spring-boot-maven-plugin in pom.xml
- Use mvn.cmd (not mvn) on Windows

## Error Recovery Examples
If mvn build fails with "Could not find artifact":
  → Check pom.xml for correct dependency coordinates

If java -jar fails with "no main manifest":
  → Check spring-boot-maven-plugin is in pom.xml <build><plugins>

If 404 on http://localhost:8080/:
  → Check @Controller has @GetMapping("/") and template exists

If "address already in use":
  → Kill the old process: run_command("taskkill /F /IM java.exe")
  → Wait: run_command("ping -n 3 127.0.0.1 >nul")
  → Then restart

## Windows Environment
- Shell commands run via cmd.exe (NOT bash/WSL)
- Use mvn.cmd (not mvn) for Maven
- Use forward slashes / in file paths for tool calls
- Java and Maven are on PATH
- To run in background: start /B command

Always explain what you're doing and why. After completing a task, summarize what was done and ask if the user needs anything else."""
        if memory_context:
            system_content += f"\n\nRelevant memories:\n{memory_context}"

        system_msg = LLMMessage(role=MessageRole.SYSTEM, content=system_content)
        return [system_msg] + list(self.messages)

    def _render_response(self, content: str) -> None:
        """Render assistant response with code highlighting."""
        # Extract and display code blocks separately
        code_pattern = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)
        parts = code_pattern.split(content)

        if len(parts) <= 1:
            # No code blocks, render as markdown
            console.print()
            console.print(Markdown(content))
            return

        # Render with mixed markdown + syntax-highlighted code
        console.print()
        i = 0
        while i < len(parts):
            text_part = parts[i].strip()
            if text_part:
                console.print(Markdown(text_part))
            if i + 1 < len(parts):
                lang = parts[i + 1] or "python"
                code = parts[i + 2]
                console.print(Syntax(code.strip(), lang, theme="monokai", line_numbers=True))
                i += 3
            else:
                i += 1

    def _show_token_bar(self, usage: dict[str, int]) -> None:
        """Show a compact token usage bar after each turn."""
        prompt = usage.get("prompt_tokens", 0)
        completion = usage.get("completion_tokens", 0)
        total = prompt + completion
        budget_used = self.budget.total_used
        budget_total = self.budget.total
        pct = budget_used / budget_total * 100 if budget_total else 0

        # Color based on threshold
        if pct >= 95:
            color = "bold red"
            warn = " [red]CRITICAL — consider /clear[/red]"
        elif pct >= 80:
            color = "bold yellow"
            warn = " [yellow]WARNING[/yellow]"
        else:
            color = "dim"
            warn = ""

        console.print(
            f"  [{color}]Tokens: +{prompt}in +{completion}out = {total} "
            f"| Total: {budget_used:,}/{budget_total:,} ({pct:.1f}%){warn}[/{color}]"
        )

    # ── Command Dispatch ────────────────────────────────────────────────

    def _handle_command(self, raw: str) -> bool:
        """Handle /commands. Returns True to quit."""
        parts = raw.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd in ("/quit", "/exit", "/q"):
            console.print("[dim]Goodbye![/dim]")
            return True

        elif cmd == "/help":
            self._cmd_help()

        elif cmd == "/memory":
            self._cmd_memory()

        elif cmd == "/budget":
            self._cmd_budget()

        elif cmd == "/security":
            asyncio.run(self._cmd_security())

        elif cmd == "/audit":
            self._cmd_audit()

        elif cmd == "/consolidate":
            self._cmd_consolidate()

        elif cmd == "/save":
            self._cmd_save(arg or "session.md")

        elif cmd == "/clear":
            self._cmd_clear()

        else:
            console.print(f"[yellow]Unknown command:[/yellow] {cmd}")
            console.print("  Type /help for available commands.")

        return False

    # ── Command Implementations ──────────────────────────────────────────

    def _cmd_help(self) -> None:
        table = Table(title="Chat Commands", show_lines=False)
        table.add_column("Command", style="bold cyan", min_width=14)
        table.add_column("Description", style="white")
        table.add_row("/help", "Show this help")
        table.add_row("/memory", "3-layer memory status")
        table.add_row("/budget", "Token budget dashboard")
        table.add_row("/security", "SAST scan on session code blocks")
        table.add_row("/audit", "View audit log")
        table.add_row("/consolidate", "Trigger memory consolidation")
        table.add_row("/save [file]", "Export session as Markdown")
        table.add_row("/clear", "Clear messages (keep memory)")
        table.add_row("/quit", "Exit")
        console.print(table)

    def _cmd_memory(self) -> None:
        """Display 3-layer memory status."""
        table = Table(title="Memory Status", show_lines=True)
        table.add_column("Layer", style="bold cyan")
        table.add_column("Metric", style="dim")
        table.add_column("Value", style="bold")

        # Working memory
        wm = self.memory.working.summary()
        table.add_row("Working", "Messages", str(wm["message_count"]))
        table.add_row("", "Tokens", str(wm["total_tokens"]))

        # Episodic memory
        em = self.memory.episodic.summary()
        table.add_row("Episodic", "Records", str(em["total_records"]))
        for t, count in em.get("by_type", {}).items():
            table.add_row("", f"  {t}", str(count))

        # Semantic memory
        sm = self.memory.semantic.summary()
        table.add_row("Semantic", "Entries", str(sm["total_entries"]))
        for cat, count in sm.get("by_category", {}).items():
            table.add_row("", f"  {cat}", str(count))

        # Graph
        gs = self.memory.graph.summary()
        table.add_row("Graph", "Nodes", str(gs["nodes"]))
        table.add_row("", "Edges", str(gs["edges"]))

        console.print(table)

    def _cmd_budget(self) -> None:
        """Display token budget dashboard."""
        snapshot = self.budget.snapshot()
        pct = snapshot.overall_utilization * 100

        table = Table(title="Token Budget", show_lines=True)
        table.add_column("Allocation", style="bold cyan")
        table.add_column("Used", justify="right")
        table.add_column("Limit", justify="right")
        table.add_column("Utilization", justify="right")
        table.add_column("Level", justify="center")

        level_colors = {
            "normal": "green",
            "warning": "yellow",
            "hard_limit": "red",
            "exceeded": "bold red",
        }

        for name, info in snapshot.allocations.items():
            used = info["used"]
            limit = info["limit"]
            util = info["utilization"] * 100
            level = info["level"]
            color = level_colors.get(level, "white")

            # Progress bar
            bar_width = 20
            filled = int(util / 100 * bar_width)
            bar = "[" + "#" * filled + "." * (bar_width - filled) + "]"

            table.add_row(
                name,
                f"{used:,}",
                f"{limit:,}",
                f"{bar} {util:.1f}%",
                f"[{color}]{level}[/{color}]",
            )

        # Total row
        table.add_row(
            "[bold]TOTAL[/bold]",
            f"[bold]{snapshot.total_used:,}[/bold]",
            f"[bold]{snapshot.total_limit:,}[/bold]",
            f"[bold]{pct:.1f}%[/bold]",
            "",
        )

        console.print(table)

        # Warning
        if pct >= 95:
            console.print("[bold red]CRITICAL: Budget nearly exhausted! Use /clear to reset.[/bold red]")
        elif pct >= 80:
            console.print("[bold yellow]WARNING: Budget usage high.[/bold yellow]")

    async def _cmd_security(self) -> None:
        """SAST scan on code blocks extracted from session."""
        code_pattern = re.compile(r"```python\n(.*?)```", re.DOTALL)
        code_blocks = []
        for msg in self.messages:
            if msg.role == MessageRole.ASSISTANT:
                for match in code_pattern.finditer(msg.content):
                    code_blocks.append(match.group(1))

        if not code_blocks:
            console.print("[dim]No Python code blocks found in session.[/dim]")
            return

        console.print(f"[cyan]Scanning {len(code_blocks)} code block(s)...[/cyan]")

        all_findings = []
        for i, code in enumerate(code_blocks):
            bf = self.bandit.scan_text(code, filename=f"block_{i+1}.py")
            sf = self.semgrep.scan_text(code, filename=f"block_{i+1}.py")
            all_findings.extend(bf)
            all_findings.extend(sf)

        if not all_findings:
            console.print("[green]No security issues found.[/green]")
            return

        table = Table(title="Security Scan Results", show_lines=True)
        table.add_column("#", style="dim", width=3)
        table.add_column("Severity", width=10)
        table.add_column("Rule", style="cyan")
        table.add_column("Line", justify="right", width=5)
        table.add_column("Description")

        sev_colors = {"CRITICAL": "bold red", "HIGH": "red", "MEDIUM": "yellow", "WARNING": "yellow", "ERROR": "red", "LOW": "dim"}

        for i, f in enumerate(all_findings):
            color = sev_colors.get(f.severity, "white")
            table.add_row(
                str(i + 1),
                f"[{color}]{f.severity}[/{color}]",
                f.rule_id,
                str(f.line_number),
                f.description[:80],
            )

        console.print(table)

        # Audit log
        from kiracode.security.audit_log import AuditEntry
        await self.audit.log(AuditEntry(
            event_type="security_scan",
            actor="user",
            action="sast_scan",
            details={"findings": len(all_findings), "code_blocks": len(code_blocks)},
        ))

    def _cmd_audit(self) -> None:
        """Display audit log entries for this session."""
        entries = self.audit.query()
        if not entries:
            console.print("[dim]No audit entries yet.[/dim]")
            return

        table = Table(title="Audit Log", show_lines=True)
        table.add_column("Time", style="dim", width=20)
        table.add_column("Event", style="cyan")
        table.add_column("Action")
        table.add_column("Details")

        for entry in entries[-20:]:  # Last 20
            ts = str(entry.timestamp)[:19] if entry.timestamp else "-"
            details = str(entry.details)[:50] if entry.details else "-"
            table.add_row(ts, entry.event_type, entry.action, details)

        console.print(table)

    def _cmd_consolidate(self) -> None:
        """Trigger memory consolidation: episodic -> semantic."""
        before = self.memory.semantic.summary()
        self.memory.consolidate()
        after = self.memory.semantic.summary()

        promoted = after["total_entries"] - before["total_entries"]
        console.print(f"[green]Consolidation complete.[/green]")
        console.print(f"  Semantic entries: {before['total_entries']} -> {after['total_entries']} (+{promoted})")

    def _cmd_save(self, filename: str) -> None:
        """Export session as Markdown."""
        lines = [
            f"# KiraCode Session",
            f"",
            f"- Session ID: {self.session_id}",
            f"- Provider: {self.provider.provider_name}",
            f"- Model: {self.provider.model}",
            f"- Rounds: {self.round_count}",
            f"- Tokens: {self.total_prompt_tokens} prompt + {self.total_completion_tokens} completion",
            f"- Saved: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            f"",
            f"---",
            f"",
        ]

        round_num = 0
        for msg in self.messages:
            if msg.role == MessageRole.USER:
                round_num += 1
                lines.append(f"## Round {round_num}")
                lines.append(f"")
                lines.append(f"**User**: {msg.content}")
                lines.append(f"")
            elif msg.role == MessageRole.ASSISTANT:
                lines.append(f"**Assistant**:")
                lines.append(f"")
                lines.append(msg.content)
                lines.append(f"")

        content = "\n".join(lines)
        path = Path(filename)
        path.write_text(content, encoding="utf-8")
        console.print(f"[green]Session saved to {path.resolve()}[/green] ({len(content)} bytes)")

    def _cmd_clear(self) -> None:
        count = len(self.messages)
        self.messages.clear()
        self.round_count = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        console.print(f"[green]Cleared {count} messages. Memory preserved.[/green]")


# ── Entry Point ─────────────────────────────────────────────────────────────


def main() -> None:
    """Entry point for `python -m kiracode.cli.chat` or `kiracode-chat`."""
    import argparse

    parser = argparse.ArgumentParser(description="KiraCode Interactive Chat")
    parser.add_argument("--provider", default="mimo", help="LLM provider (mimo/dashscope/openai/anthropic/mock)")
    parser.add_argument("--model", default="mimo-v2.5-pro", help="Model name")
    parser.add_argument("--budget", type=int, default=128000, help="Token budget")
    parser.add_argument("--api-key", default="", help="API key (or set ANTHROPIC_AUTH_TOKEN env var)")
    args = parser.parse_args()

    session = ChatSession(
        provider_name=args.provider,
        model=args.model,
        max_budget=args.budget,
        api_key=args.api_key,
    )
    session.run()


if __name__ == "__main__":
    main()
