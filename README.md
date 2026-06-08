# KiraCode

> **AI Coding Agent** — autonomous code generation, build, and execution with self-healing capabilities.

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)
![Pydantic](https://img.shields.io/badge/Pydantic-v2-red)
![Rich](https://img.shields.io/badge/Rich-CLI-brightgreen)
![pytest](https://img.shields.io/badge/pytest-167%20tests-yellow)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

---

## What is KiraCode?

KiraCode is an autonomous AI coding agent that can:

- **Generate complete projects** — Spring Boot, frontend, or any project from natural language
- **Build and run automatically** — creates files, runs build commands, starts servers
- **Self-heal on errors** — reads error messages, fixes code, and retries (up to 5 times)
- **Continue conversations** — summarizes results and asks what's next
- **Think step-by-step** — shows reasoning process before executing actions

Powered by **MiMo v2.5 Pro** (Xiaomi) via Anthropic-compatible API.

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/luozhonglzw/mini-kira-code.git
cd mini-kira-code

# 2. Install
pip install -e .

# 3. Configure API key
cp .env.example .env
# Edit .env and fill in your API key

# 4. Run
python -m kiracode.cli.chat
```

Then just ask KiraCode to build something:

```
You: 请帮我创建一个 Spring Boot + 前端项目，包含首页和 /hello 接口
```

KiraCode will:
1. Create all project files (pom.xml, Java sources, templates, static assets)
2. Build with `mvn.cmd clean package`
3. Fix any build errors automatically
4. Start the server and report the URL

---

## Architecture

```
User Input
    │
    ▼
┌─────────────────────────────┐
│  ChatSession (REPL)         │  Interactive CLI with Rich rendering
│  - Multi-turn conversation  │
│  - Memory (3-layer)         │
│  - Token budget tracking    │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│  LLM Provider               │  MiMo v2.5 Pro (Anthropic-compatible)
│  - Tool calling (function)  │  DashScope / OpenAI / Anthropic also supported
│  - Thinking/reasoning       │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│  Tool Execution Loop        │  Up to 30 rounds per turn
│  - write_file               │
│  - read_file                │
│  - run_command              │
│  - Self-heal on failure     │
│  - Forced summary on exit   │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│  Sandbox (cmd.exe / bash)   │  Isolated execution
│  - Timeout: 300s (600s)     │  Working dir: project root
│  - Path security            │  All ops restricted to project dir
└─────────────────────────────┘
```

---

## Features

### Autonomous Tool Calling
KiraCode uses OpenAI-compatible function calling to execute real actions:
- `write_file(path, content)` — create files with auto-mkdir
- `read_file(path)` — read file contents
- `run_command(command)` — execute shell commands in sandbox

### Self-Healing
When a build or command fails:
1. Reads the error message (stdout + stderr)
2. Analyzes the root cause
3. Fixes the code
4. Retries (up to 5 times per error)

### Thinking Process
KiraCode shows its reasoning before acting:
```
Thinking: The user wants a Spring Boot project. I need to create:
1. pom.xml with dependencies
2. Application main class
3. Controller with /hello endpoint
4. HTML template...
```

### Multi-Provider Support
| Provider | Model | Status |
|----------|-------|--------|
| MiMo (Xiaomi) | mimo-v2.5-pro | Default |
| DashScope (Alibaba) | qwen-max | Supported |
| OpenAI | gpt-4o | Supported |
| Anthropic | claude-sonnet | Supported |
| Mock | mock-model | Testing |

---

## Project Structure

```
mini-kira-code/
├── kiracode/
│   ├── cli/
│   │   ├── app.py           # Click CLI entry point
│   │   └── chat.py          # Interactive REPL with tool calling
│   ├── llm/
│   │   ├── base.py          # Abstract LLM provider
│   │   ├── mimo_provider.py # MiMo (Anthropic-compatible)
│   │   ├── dashscope_provider.py # DashScope (OpenAI-compatible)
│   │   └── factory.py       # Provider factory
│   ├── skills/
│   │   ├── builtin/
│   │   │   ├── file_ops.py  # File read/write with path security
│   │   │   ├── shell_exec.py # Command execution via cmd.exe
│   │   │   └── screenshot_analyze.py # Vision analysis
│   │   ├── registry.py      # Skill registry
│   │   └── router.py        # Semantic routing
│   ├── security/
│   │   └── sandbox.py       # Subprocess isolation with cwd support
│   ├── agents/              # Multi-agent system
│   ├── memory/              # 3-layer cognitive memory
│   ├── context/             # Context compression
│   └── core/                # Config, event bus, token budget
├── tests/                   # 167 tests
├── configs/                 # YAML configuration
├── docs/                    # Documentation
└── pyproject.toml
```

---

## Running Tests

```bash
python -m pytest tests/ -v
```

167 tests covering:
- LLM providers (MiMo, DashScope, OpenAI)
- Tool execution and sandbox
- Memory system
- Security scanning
- Configuration

---

## Configuration

Default config in `configs/default.yaml`:

```yaml
llm:
  provider: "mimo"
  model: "mimo-v2.5-pro"
  temperature: 0.7
  max_tokens: 4096
  timeout: 300
```

Override via CLI:
```bash
python -m kiracode.cli.chat --provider dashscope --model qwen-max
```

---

## Documentation

- [docs/DEMO.md](docs/DEMO.md) — Real demo: KiraCode builds a Spring Boot project autonomously
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — Architecture design, Mermaid diagrams
- [docs/ENV.md](docs/ENV.md) — Environment setup, Docker, configuration
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) — Development guide, testing, debugging

---

## License

MIT
