# KiraCode 开发指南

## 1. 开发规范

### 代码风格

- **Python 3.10+** 类型注解强制：所有函数签名必须有参数类型和返回类型
- **Pydantic v2** 数据校验优先：所有数据模型继承 `BaseModel`
- **异步优先**：核心路径使用 `async/await`，避免阻塞调用
- **Ruff 格式化**：`ruff check kiracode/ --fix` + `ruff format kiracode/`

### 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| 文件名 | snake_case | `event_bus.py` |
| 类名 | PascalCase | `TokenBudgetManager` |
| 函数/变量 | snake_case | `count_tokens()` |
| 常量 | UPPER_SNAKE_CASE | `SECRET_PATTERNS` |
| 私有属性 | _leading_underscore | `_total_tokens`（Pydantic 用 `PrivateAttr`） |

### Pydantic v2 私有属性规则

```python
from pydantic import BaseModel, PrivateAttr

class MyModel(BaseModel):
    public_field: str = "ok"           # 正常字段
    _internal: int = PrivateAttr(default=0)  # 私有属性（不序列化）
```

**注意**：Pydantic v2 禁止用 `_` 前缀做字段名，必须用 `PrivateAttr`。

## 2. 测试

### 运行测试

```bash
# 全部测试
pytest tests/ -v

# 带覆盖率
pytest tests/ -v --cov=kiracode --cov-report=term-missing

# 只跑单元测试
pytest tests/ -v -m unit

# 只跑某个文件
pytest tests/test_memory.py -v

# 并行执行（需安装 pytest-xdist）
pytest tests/ -v -n auto
```

### 编写测试规范

```python
import pytest
from kiracode.memory.working import WorkingMemory, Message, MessageRole

@pytest.mark.unit
def test_working_memory_push():
    wm = WorkingMemory(max_tokens=1000)
    wm.push(Message(role=MessageRole.USER, content="hello"))
    assert wm.total_tokens > 0
    assert len(wm.messages) == 1

@pytest.mark.asyncio
async def test_event_bus_publish():
    from kiracode.core.event_bus import EventBus
    bus = EventBus()
    results = []
    async def handler(event):
        results.append(event.type)
    bus.subscribe("test", handler)
    await bus.emit("test", {"key": "value"})
    assert "test" in results
```

## 3. 如何添加新 Agent

### 步骤

1. 在 `kiracode/agents/` 下创建新文件：

```python
# kiracode/agents/my_agent.py
from kiracode.agents.base import Agent, AgentContext, AgentResult

class MyAgent(Agent):
    def __init__(self):
        super().__init__("my_agent")

    async def plan(self, ctx: AgentContext) -> dict:
        return {"phase": "my_planning"}

    async def execute(self, ctx: AgentContext) -> dict:
        # Your logic here
        return {"result": "done", "output_lines": 42}

    async def review(self, ctx: AgentContext, result: AgentResult) -> bool:
        return True  # enter REVIEWING state
```

2. 在 `kiracode/agents/__init__.py` 中导出：

```python
from kiracode.agents.my_agent import MyAgent
```

3. 在 Architect 的 `_mock_plan_decompose()` 中添加路由规则：

```python
if "my_task" in query_lower:
    subtasks.append(SubTask(agent_type="my_agent", description="..."))
```

## 4. 如何添加 Skill 插件

### 步骤

1. 在 `kiracode/skills/builtin/` 或 `.kiracode/skills/` 下创建文件：

```python
# kiracode/skills/builtin/my_skill.py
from kiracode.skills.registry import SkillMeta

skill_meta = SkillMeta(
    name="my_skill",
    description="Does something useful",
    tags=["tag1", "tag2"],
    capabilities=["cap1"],
    source="builtin",
)

class SkillClass:
    async def execute(self, **kwargs) -> dict:
        return {"status": "ok", "data": kwargs}
```

2. 重新运行程序，`SkillLoader` 会自动发现并加载。

### 热加载

```python
from kiracode.skills.loader import SkillLoader
from kiracode.skills.registry import registry

loader = SkillLoader(registry)
loader.reload_all()  # 重新扫描所有目录
```

## 5. 调试技巧

### 查看 EventBus 消息流

```python
import logging
logging.basicConfig(level=logging.DEBUG)

from kiracode.core.event_bus import EventBus
bus = EventBus()
# ... 运行后查看日志输出中的 "Subscribed" 和 event 发布记录
print(bus.get_history(limit=20))
```

### 查看 Token 预算实时消耗

```python
from kiracode.core.token_budget import TokenBudgetManager
budget = TokenBudgetManager(total=128000)
# ... 运行后
for a in budget.list_allocations():
    print(f"{a.name}: {a.used}/{a.limit} ({a.utilization:.1%}) [{a.level.value}]")
```

### 查看记忆状态

```python
from kiracode.memory.manager import MemoryManager
mgr = MemoryManager()
# ... 运行后
import json
print(json.dumps(mgr.full_summary(), indent=2, default=str))
```

### 查看上下文压缩效果

```python
from kiracode.context.compressor import SmartCompressor
comp = SmartCompressor()
# ... 压缩后
print(comp.stats())  # compressed_count, saved_tokens, stored_references
```

## 6. 性能剖析

```bash
# cProfile 分析
python -m cProfile -s cumulative demo_full.py | head -30

# 基于行的分析（需安装 line_profiler）
kernprof -l -v demo_full.py

# 内存分析（需安装 memory_profiler）
python -m memory_profiler demo_full.py
```

## 7. 项目文件清单

| 文件 | 行数 | 职责 |
|------|------|------|
| `core/config.py` | ~150 | Pydantic Settings + YAML + 环境变量 |
| `core/event_bus.py` | ~130 | 异步事件总线 + 历史 + wildcard |
| `core/token_budget.py` | ~160 | 预算池 + 分 allocation + 阈值回调 |
| `agents/base.py` | ~200 | Agent ABC + 状态机 + run() 生命周期 |
| `agents/architect.py` | ~230 | Architect + Coder + Reviewer (Mock) |
| `memory/working.py` | ~92 | 工作记忆 + Token 计数 |
| `memory/episodic.py` | ~107 | 情景记忆 + TaskRecord |
| `memory/semantic.py` | ~114 | 语义记忆 + 伪向量检索 |
| `memory/graph.py` | ~140 | NetworkX 记忆图谱 |
| `memory/manager.py` | ~147 | 统一管理器 + consolidate |
| `context/window.py` | ~143 | 滑动窗口 + 自动压缩触发 |
| `context/compressor.py` | ~198 | 智能压缩 + 引用追踪 |
| `security/sandbox.py` | ~100 | subprocess 隔离执行 |
| `security/secrets_scanner.py` | ~150 | 10 种模式 + 熵检测 |
| `security/audit_log.py` | ~90 | JSONL 审计日志 |
| `security/rollback.py` | ~90 | 文件快照 + 回滚 |
| `skills/registry.py` | ~90 | 注册中心 |
| `skills/loader.py` | ~90 | 动态加载器 |
| `skills/router.py` | ~100 | 语义路由 |
| `skills/builtin/*.py` | ~200 | 4 个内置 Skill |
| `cli/app.py` | ~170 | Rich REPL |
| `utils/token_counter.py` | ~19 | Token 计数器 |
