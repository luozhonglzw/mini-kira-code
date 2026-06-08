# KiraCode — Resume & Interview Preparation

## Resume Bullet Points (STAR Format)

### Bullet 1: Multi-Agent Architecture
> Designed and implemented a hierarchical multi-agent system (Architect → Coder → Reviewer) with async event-driven communication, achieving 10x task decomposition capability. Built state machine enforcing IDLE→PLANNING→EXECUTING→REVIEWING→DONE transitions with automatic retry and rollback on failure.

**Keywords**: Multi-Agent, State Machine, Event-Driven, Async, Pydantic

### Bullet 2: Security-First DevSecOps Pipeline
> Integrated 36 SAST rules (Bandit + Semgrep style) and SARIF v2.1.0 report generation into the agent pipeline, enabling automated vulnerability detection before code execution. Built MITRE ATT&CK-based pentest script generator supporting 5 attack techniques with safety review gates.

**Keywords**: SAST, SARIF, MITRE ATT&CK, DevSecOps, Security Automation

### Bullet 3: Context Governance & Memory System
> Engineered a three-layer cognitive memory (Working + Episodic + Semantic) with NetworkX knowledge graph, combined with sliding-window context compression achieving 95%+ token savings. Implemented token budget manager with warning/hard thresholds across 4 allocation pools.

**Keywords**: Memory Architecture, Context Compression, Token Budget, Knowledge Graph

---

## Interview Q&A

### Q1: Why a hierarchical multi-agent architecture instead of a single LLM call?

**Answer**: A single LLM call has three problems: (1) **context window limits** — complex tasks exceed token budgets; (2) **no separation of concerns** — planning, coding, and reviewing need different reasoning styles; (3) **no retry granularity** — a single failure means restarting everything.

KiraCode's hierarchy solves this: the **Architect** decomposes queries into subtasks with dependency graphs, the **Coder** generates code per subtask (resettable for reuse), and the **Reviewer** validates output independently. Each agent has its own state machine, so failures are isolated. The **EventBus** enables loose coupling — agents communicate via events, not direct calls, making it easy to add new agents (like the PentestAgent) without modifying existing ones.

### Q2: How does the context compression work and why 95% savings?

**Answer**: The `SmartCompressor` uses format-specific strategies:

1. **JSON**: Extracts only changed keys instead of full objects
2. **Log**: Keeps first/last N lines + error lines, drops repetitive INFO entries
3. **Text**: Summarizes to key sentences using keyword extraction

The sliding window keeps recent messages intact while compressing older ones. A `ReferenceStore` preserves original content for decompression. The 95% figure comes from compressing 10,549 tokens of mixed JSON/log/text down to 472 tokens — realistic because agent conversations accumulate verbose tool outputs that are highly compressible.

### Q3: How do you prevent the generated code from being harmful?

**Answer**: Multiple layers:

1. **Secrets Scanner**: 10 regex patterns + Shannon entropy detection before any code execution
2. **SAST Rules**: 36 rules (Bandit + Semgrep) scan for SQL injection, hardcoded secrets, unsafe deserialization, etc.
3. **Sandbox**: subprocess isolation with timeout and memory limits
4. **PentestAgent Safety Review**: checks for destructive patterns (rm -rf, DROP TABLE) before marking scripts as safe
5. **Audit Log**: JSONL append-only log of all security-relevant events

The key insight is **defense in depth** — no single layer is sufficient, but together they catch different threat classes.

### Q4: Explain the token budget management system.

**Answer**: `TokenBudgetManager` divides the total context window into 4 pools:
- **system** (5%): reserved for system prompts
- **agent** (45%): agent reasoning and planning
- **tool** (30%): tool call results
- **reserve** (20%): emergency buffer

Each pool has two thresholds:
- **warning** (85%): emits event, agents can compress context
- **hard limit** (95%): rejects further consumption

This prevents any single agent from monopolizing the context window. The `consume()` method returns a `BudgetLevel` enum, so callers can react to threshold crossings.

### Q5: How would you scale this to production?

**Answer**: Three areas:

1. **LLM Integration**: Replace `MockProvider` with real providers via the factory pattern. The `LLMProvider` ABC ensures all agents work with any provider (OpenAI, Anthropic, local models). Config-driven via `configs/default.yaml`.

2. **Persistent Memory**: Replace in-memory `SemanticMemory` with ChromaDB for vector search. The `EpisodicMemory` already uses JSONL for persistence. The `MemoryGraph` can serialize to GraphML.

3. **Distributed Execution**: The EventBus is currently in-process but designed for extension — replace with Redis Streams or NATS for multi-process deployment. The `AgentContext` is serializable (Pydantic), so it can be sent across processes.

---

## 30-Second Elevator Pitch

> KiraCode is a hierarchical multi-agent AI coding system that decomposes complex tasks into subtasks, generates code, and reviews it automatically. It features a three-layer cognitive memory system, 95% context compression, 36 SAST security rules, and MITRE ATT&CK-based penetration testing — all built with async Python, Pydantic v2, and zero external dependencies for the core.

---

## 2-Minute Project Deep Dive

**Problem**: Single LLM calls fail on complex coding tasks due to context limits, no separation of planning/coding/reviewing, and no security guarantees.

**Solution**: KiraCode implements a 4-layer architecture:

1. **Core Layer**: EventBus (async pub/sub), TokenBudgetManager (4-pool allocation), Config (YAML + env vars)
2. **Agent Layer**: State machine (IDLE→PLANNING→EXECUTING→REVIEWING→DONE), Architect/Coder/Reviewer/PentestAgent with dependency-aware execution
3. **Memory Layer**: Working (session) + Episodic (task history) + Semantic (knowledge) + Graph (NetworkX relationships)
4. **Security Layer**: Sandbox isolation, SAST scanning (36 rules), Secrets detection (10 patterns + entropy), Audit logging, Rollback

**Key Metrics**:
- 94 tests passing in 1.87s
- 95.5% context compression (10,549 → 472 tokens)
- 36 SAST rules covering OWASP Top 10
- 5 MITRE ATT&CK techniques for pentest automation
- 8 Python files per subsystem, ~3,500 lines total

**Tech Stack**: Python 3.10+, Pydantic v2, asyncio, NetworkX, Rich, Click, tiktoken, httpx

---

## Project Highlights for Discussion

### Highlight 1: Event-Driven Agent Communication
The `EventBus` uses async generators with wildcard pattern matching (`agent.*`). This decouples agents completely — the PentestAgent was added without modifying any existing agent code. The event history buffer enables debugging and replay.

### Highlight 2: Smart Context Compression
Three format-specific strategies (JSON diff, log summarization, text extraction) with a reference store for decompression. The compressor is pluggable — new strategies can be added by implementing a single `compress()` method.

### Highlight 3: Security-as-Code
36 SAST rules are defined as Python dataclasses, not configuration files. This means they're type-checked, testable, and composable. The SARIF output integrates directly with GitHub Code Scanning and GitLab SAST.

### Highlight 4: Pydantic v2 Throughout
Every data model uses Pydantic v2 — `BaseModel` for serialization, `PrivateAttr` for runtime state, `Field` for validation. This gives us free JSON serialization, schema generation, and type safety across the entire system.
