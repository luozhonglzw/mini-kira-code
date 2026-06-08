# KiraCode 环境配置文档

## 1. 环境要求

| 项目 | 最低要求 | 推荐 |
|------|---------|------|
| Python | 3.10+ | 3.11+ |
| 内存 | 4 GB | 8 GB+ |
| 磁盘 | 100 MB | 500 MB（含 RAG 索引） |
| 操作系统 | Windows 10+ / macOS 12+ / Ubuntu 20.04+ | — |

## 2. 安装步骤

### 方式一：pip 安装

```bash
cd D:\agent\agent-project-codex-7

# 创建虚拟环境（推荐）
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

# 基础安装
pip install -e .

# 开发模式（含测试工具）
pip install -e ".[dev]"

# 全部依赖（含 RAG：Chroma + tree-sitter）
pip install -e ".[all]"
```

### 方式二：Docker

```bash
# 构建镜像
docker build -t kiracode .

# 运行演示
docker run -it kiracode python demo_full.py

# 启动交互式 CLI
docker run -it kiracode python -m kiracode.cli.app

# 单次查询
docker run -it kiracode python -m kiracode.cli.app -q "写一个排序函数"
```

### Docker Compose

```bash
docker-compose up
```

## 3. 配置文件说明

### configs/default.yaml 完整字段

```yaml
# ── 应用配置 ──────────────────────────────────────────────
app:
  name: "KiraCode"           # 应用名称
  version: "0.1.0"           # 版本号
  log_level: "INFO"          # 日志级别：DEBUG | INFO | WARNING | ERROR
  log_format: "json"         # 日志格式：json | console

# ── LLM 配置 ──────────────────────────────────────────────
llm:
  provider: "mock"           # 提供商：mock | openai | anthropic
  model: "mock-model"        # 模型名称（如 gpt-4o, claude-sonnet-4-6）
  temperature: 0.7           # 生成温度（0.0-2.0）
  max_tokens: 4096           # 单次生成最大 token 数
  timeout: 60                # API 超时秒数

# ── Agent 配置 ────────────────────────────────────────────
agents:
  architect:
    enabled: true            # 是否启用 Architect Agent
    max_subtasks: 10         # 最大子任务数
    planning_strategy: "decompose"  # 规划策略：decompose | incremental
  coder:
    enabled: true
    max_retries: 3           # 代码生成失败重试次数
    sandbox_enabled: true    # 是否在沙箱中执行生成的代码
  reviewer:
    enabled: true
    strict_mode: false       # 严格模式（任何 warning 都阻断）
  security_auditor:
    enabled: true
    scan_secrets: true       # 是否扫描密钥
    scan_sast: true          # 是否执行静态分析

# ── 记忆配置 ──────────────────────────────────────────────
memory:
  working_memory:
    max_items: 50            # 工作记忆最大消息数
    ttl_seconds: 3600        # 消息存活时间（秒）
  episodic_memory:
    max_entries: 1000        # 情景记忆最大记录数
    persistence_path: ".kiracode/memory/episodic.jsonl"  # 持久化路径
  semantic_memory:
    embedding_dim: 384       # 嵌入维度
    persistence_path: ".kiracode/memory/semantic.index"  # 索引路径
  graph:
    enabled: true            # 是否启用记忆图谱
    max_nodes: 5000          # 最大节点数

# ── 上下文配置 ────────────────────────────────────────────
context:
  max_tokens: 128000         # 上下文窗口最大 token 数
  reserve_tokens: 4096       # 预留 token（用于系统提示）
  compression_threshold: 0.8 # 压缩触发阈值（80% 时开始压缩）
  strategy: "sliding_window" # 窗口策略：sliding_window | smart_compress

# ── Token 预算配置 ────────────────────────────────────────
token_budget:
  total: 128000              # 总预算
  agent_reserve: 8192        # Agent 预留
  tool_reserve: 16384        # 工具预留
  warning_threshold: 0.85    # 告警阈值
  hard_limit: 0.95           # 硬限制

# ── 安全配置 ──────────────────────────────────────────────
security:
  sandbox:
    enabled: true
    timeout: 30              # 沙箱执行超时（秒）
    max_memory_mb: 512       # 最大内存（MB）
  secrets_scanner:
    enabled: true
    entropy_threshold: 4.5   # Shannon 熵阈值
  audit_log:
    enabled: true
    path: ".kiracode/audit/audit.jsonl"  # 审计日志路径
  rollback:
    enabled: true
    strategy: "git"          # 回滚策略：git | snapshot

# ── Skill 配置 ────────────────────────────────────────────
skills:
  auto_discover: true        # 自动发现插件
  directories:               # 插件扫描目录
    - "kiracode/skills/builtin"
    - ".kiracode/skills"
  rag:
    enabled: true
    top_k: 5                 # 检索返回数
    score_threshold: 0.6     # 最低相似度阈值

# ── CLI 配置 ──────────────────────────────────────────────
cli:
  theme: "dark"              # 主题：dark | light
  show_token_usage: true     # 显示 Token 使用
  show_agent_state: true     # 显示 Agent 状态
```

## 4. 环境变量覆盖

所有配置项均可通过环境变量覆盖，前缀 `KIRACODE_`，层级分隔符 `__`：

| 环境变量 | 对应配置项 | 示例值 |
|---------|-----------|--------|
| `KIRACODE_LLM__PROVIDER` | llm.provider | `openai` |
| `KIRACODE_LLM__MODEL` | llm.model | `gpt-4o` |
| `KIRACODE_APP__LOG_LEVEL` | app.log_level | `DEBUG` |
| `KIRACODE_TOKEN_BUDGET__TOTAL` | token_budget.total | `64000` |
| `KIRACODE_SECURITY__SANDBOX__TIMEOUT` | security.sandbox.timeout | `60` |
| `KIRACODE_CONTEXT__MAX_TOKENS` | context.max_tokens | `32000` |

```bash
# 示例：切换到 OpenAI 并开启 DEBUG 日志
export KIRACODE_LLM__PROVIDER=openai
export KIRACODE_LLM__MODEL=gpt-4o
export KIRACODE_APP__LOG_LEVEL=DEBUG
python demo.py
```

## 5. Docker 配置

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml .
COPY configs/ configs/
COPY kiracode/ kiracode/
COPY demo*.py ./

RUN pip install --no-cache-dir -e .

# 非 root 用户运行
RUN useradd -m kiracode
USER kiracode

CMD ["python", "demo_full.py"]
```

### docker-compose.yml

```yaml
version: "3.8"
services:
  kiracode:
    build: .
    volumes:
      - ./configs:/app/configs
      - ./.kiracode:/app/.kiracode
    environment:
      - KIRACODE_LLM__PROVIDER=mock
      - KIRACODE_APP__LOG_LEVEL=INFO
    stdin_open: true
    tty: true
```

## 6. 常见问题

### Q: Windows 下沙箱执行报权限错误？

A：确保当前用户有创建子进程的权限。在某些企业环境中，可能需要以管理员身份运行，或调整组策略中"允许创建子进程"的设置。

### Q: 如何切换到持久化向量库？

A：安装 Chroma 后，在配置中指定持久化路径：
```python
import chromadb
client = chromadb.PersistentClient(path=".kiracode/chroma_db")
```

### Q: tiktoken 安装失败？

A：tiktoken 需要 Rust 编译环境。Windows 用户可安装预编译包：
```bash
pip install tiktoken --only-binary=tiktoken
```
