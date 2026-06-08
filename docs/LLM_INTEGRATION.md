# LLM Integration Guide

## Quick Start

### 1. Using Mock Provider (Default - No API Key Needed)

```python
from kiracode.llm.factory import create_provider
from kiracode.llm.base import LLMMessage, MessageRole

provider = create_provider("mock")
messages = [LLMMessage(role=MessageRole.USER, content="Hello")]
response = await provider.chat(messages)
print(response.content)
```

### 2. Using OpenAI Provider

```bash
# Set API key
export OPENAI_API_KEY="sk-..."
```

```python
provider = create_provider("openai", model="gpt-4o")
response = await provider.chat(messages)
```

### 3. Using Anthropic Provider

```bash
# Set API key
export ANTHROPIC_API_KEY="sk-ant-..."
```

```python
provider = create_provider("anthropic", model="claude-sonnet-4-20250514")
response = await provider.chat(messages)
```

### 4. Using MiMo Provider (Xiaomi)

```bash
# Set API key (format: tp-xxxx)
export MIMO_API_KEY="tp-your-key-here"
```

```python
# Default: thinking mode OFF (recommended for Agent/tool-call use)
provider = create_provider("mimo", model="mimo-v2.5-pro")
response = await provider.chat(messages)

# Enable thinking mode (for deep reasoning tasks, single-turn preferred)
provider = create_provider("mimo", model="mimo-v2.5-pro", thinking_mode=True)
```

**Connectivity test**:
```bash
python scripts/test_mimo_connection.py
```

---

## Architecture

```
kiracode/llm/
    __init__.py          # Public API exports
    base.py              # LLMProvider ABC, LLMMessage, LLMResponse
    mock_provider.py     # MockProvider for testing
    openai_provider.py   # OpenAI/compatible API provider
    anthropic_provider.py # Anthropic Claude provider
    mimo_provider.py     # Xiaomi MiMo Token Plan API provider
    factory.py           # create_provider() factory function
```

### Key Design Decisions

1. **Async-First**: All LLM calls are `async` for non-blocking execution in the agent pipeline.
2. **No SDK Dependencies**: Uses `httpx` directly instead of provider SDKs to minimize dependencies.
3. **Unified Message Format**: `LLMMessage` abstracts provider-specific message formats.
4. **Lazy Import**: Provider modules are imported only when created (avoids import errors for unused providers).

---

## Configuration Integration

### Update `configs/default.yaml`

```yaml
llm:
  provider: "openai"        # "mock", "openai", "anthropic"
  model: "gpt-4o"           # Model identifier
  temperature: 0.7
  max_tokens: 4096
  timeout: 60
  api_key_env: "OPENAI_API_KEY"  # Environment variable name for API key
  base_url: ""              # Custom endpoint (for Azure, vLLM, etc.)
```

### Update `kiracode/core/config.py`

Add to `LLMConfig`:

```python
class LLMConfig(BaseModel):
    provider: str = "mock"
    model: str = "mock-model"
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: int = 60
    api_key_env: str = ""   # NEW: env var name for API key
    base_url: str = ""      # NEW: custom endpoint URL
```

---

## Modification Checklist

### Step 1: Replace Mock LLM in Agents

**File**: `kiracode/agents/architect.py`

```python
# Before (Mock):
class ArchitectAgent(Agent):
    async def plan(self, ctx: AgentContext) -> dict[str, Any]:
        # ... hardcoded logic

# After (Real LLM):
class ArchitectAgent(Agent):
    def __init__(self, llm: LLMProvider | None = None):
        super().__init__("architect")
        self._llm = llm or create_provider("mock")

    async def plan(self, ctx: AgentContext) -> dict[str, Any]:
        messages = [
            LLMMessage(role=MessageRole.SYSTEM, content=PLANNING_PROMPT),
            LLMMessage(role=MessageRole.USER, content=ctx.query),
        ]
        response = await self._llm.chat(messages)
        # Parse response.content as JSON plan
        return json.loads(response.content)
```

### Step 2: Add LLM Provider to Agent Context

**File**: `kiracode/agents/base.py`

```python
class AgentContext(BaseModel):
    query: str = ""
    task_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    memory: Any = None
    event_bus: Any = None
    token_budget: Any = None
    llm: Any = None  # NEW: LLM provider instance
```

### Step 3: Wire Provider in Orchestrator

**File**: `kiracode/cli/app.py` or main orchestrator

```python
from kiracode.llm.factory import create_provider
from kiracode.core.config import load_config

config = load_config()
llm = create_provider(
    provider=config.llm.provider,
    model=config.llm.model,
)

# Pass to agents
ctx = AgentContext(query=query, llm=llm)
result = await agent.run(ctx)
```

### Step 4: Add tiktoken for Accurate Token Counting

**Install**:
```bash
pip install tiktoken
```

**Usage** (already integrated in `utils/token_counter.py`):
```python
from kiracode.utils.token_counter import count_tokens

# Uses tiktoken if installed, falls back to heuristic
token_count = count_tokens("Hello, world!", model="gpt-4o")
```

---

## Provider-Specific Notes

### OpenAI Compatible Endpoints

```python
# Azure OpenAI
provider = create_provider(
    "openai",
    model="gpt-4",
    base_url="https://YOUR_RESOURCE.openai.azure.com/openai/deployments/YOUR_DEPLOYMENT",
    api_key="your-azure-key",
)

# Local vLLM
provider = create_provider(
    "openai",
    model="meta-llama/Llama-3-8B",
    base_url="http://localhost:8000/v1",
    api_key="not-needed",
)

# Ollama
provider = create_provider(
    "openai",
    model="llama3",
    base_url="http://localhost:11434/v1",
    api_key="not-needed",
)
```

### Anthropic Streaming

```python
provider = create_provider("anthropic")
async for chunk in provider.stream(messages):
    print(chunk, end="", flush=True)
```

### MiMo (Xiaomi) Important Notes

**Pit 1 — Thinking Mode**:
- MiMo's thinking mode is ON by default, consuming extra tokens
- KiraCode defaults to `thinking_mode=False` to avoid 400 errors on multi-turn tool calls
- If you enable thinking mode, use it for single-turn reasoning tasks only

**Pit 2 — reasoning_content Round-Trip**:
- When thinking mode is enabled, MiMo returns `reasoning_content` in the response
- On multi-turn tool calls, you MUST pass back the assistant's `reasoning_content`
- MimoProvider handles this automatically via `_reasoning_cache`
- If cache miss occurs with thinking enabled, a placeholder is injected to avoid 400

**Error Codes**:
| Code | Meaning | Action |
|------|---------|--------|
| 400  | Param Incorrect (usually missing reasoning_content) | Check multi-turn message format |
| 429  | Rate Limited | Wait and retry |
| 502  | Gateway Error | MiMo API temporarily unavailable |

**Model Selection**:
- `mimo-v2.5-pro`: Best for reasoning, Agent tasks, code generation
- `mimo-v2.5`: Multimodal (text + image understanding)

**Configuration** (`configs/default.yaml`):
```yaml
llm:
  provider: mimo
  mimo_api_key: ""           # or set MIMO_API_KEY env var
  mimo_model: "mimo-v2.5-pro"
  mimo_base_url: "https://token-plan-cn.xiaomimimo.com/v1"
  mimo_thinking_mode: false   # keep OFF for Agent use
```

---

## Token Budget Integration

```python
from kiracode.core.token_budget import TokenBudgetManager
from kiracode.llm.factory import create_provider

budget = TokenBudgetManager(total=128000)
llm = create_provider("openai", model="gpt-4o")

# Before LLM call
msg_tokens = await llm.count_tokens(messages)
budget.consume("planning", msg_tokens)

# After LLM call
budget.consume("planning", response.usage["completion_tokens"])
```

---

## Chroma Persistence Migration (Future)

When migrating from in-memory semantic search to ChromaDB:

```python
# Install
# pip install chromadb

# Replace SemanticMemory with Chroma-backed version
import chromadb

class ChromaSemanticMemory:
    def __init__(self, collection_name: str = "kiracode"):
        self._client = chromadb.PersistentClient(path=".kiracode/chroma")
        self._collection = self._client.get_or_create_collection(collection_name)

    def add(self, content: str, metadata: dict = {}):
        self._collection.add(
            documents=[content],
            metadatas=[metadata],
            ids=[hash(content)]
        )

    def search(self, query: str, top_k: int = 5):
        results = self._collection.query(query_texts=[query], n_results=top_k)
        return results["documents"][0]
```
