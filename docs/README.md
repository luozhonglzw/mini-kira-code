# KiraCode

> **基于分层规划架构的 AI Coding Agent 系统** — 让多个 Agent 协作完成代码生成、审查、安全审计的完整工程闭环。

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)
![Pydantic](https://img.shields.io/badge/Pydantic-v2-red)
![Rich](https://img.shields.io/badge/Rich-CLI-brightgreen)
![NetworkX](https://img.shields.io/badge/NetworkX-Graph-orange)
![pytest](https://img.shields.io/badge/pytest-Tested-yellow)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

---

## 核心特性

- **分层规划架构** — Architect Agent 将用户自然语言查询分解为带依赖关系的子任务图，分配给 Coder / Reviewer / SecurityAuditor 并行或串行执行
- **事件驱动引擎** — 模块间通过异步 EventBus 解耦，支持 publish/subscribe、wildcard 匹配、事件历史回溯
- **三层认知记忆** — 工作记忆（当前会话 Token 预算管理）+ 情景记忆（历史 TaskRecord 执行轨迹）+ 语义记忆（抽象知识模式 + 向量检索）+ NetworkX 记忆图谱
- **上下文治理** — Token 预算管理器 + 智能压缩器（95%+ 压缩率）+ 引用追踪按需还原
- **插件化 Skill** — 动态加载 + 语义路由 + 4 个内置 Skill（file_ops / shell_exec / code_search / git_ops）
- **安全审计** — 独立 Security Auditor Agent + Secrets 扫描（10 种模式 + 熵检测）+ 沙箱执行 + JSONL 审计日志 + 文件快照回滚
- **多模态视觉** — 基于 Qwen-VL（阿里云百炼）的 UI 截图分析，支持 OpenCV 预处理 + YOLOv8-nano 元素检测，输出结构化组件/布局/配色描述，驱动 Agent 生成前端代码

---

## 多模态视觉能力

### 架构

```
用户输入: "用 React 实现这个界面" + UI 截图.png
           │
           ▼
┌─────────────────────────────┐
│  _extract_image_input()     │  检测图片路径 / base64
│  _has_vision_intent()       │  检测视觉关键词
└──────────┬──────────────────┘
           ▼
┌─────────────────────────────┐
│  OpenCV Preprocessing       │  resize 1024x1024 / 去噪
│  (detail_level: fast/       │  / 边缘检测（detailed）
│   standard/detailed)        │
└──────────┬──────────────────┘
           ▼
┌─────────────────────────────┐
│  Qwen-VL API (百炼)         │  结构化 Prompt → JSON
│  + (可选) YOLOv8-nano       │  本地 UI 元素检测
└──────────┬──────────────────┘
           ▼
┌─────────────────────────────┐
│  Structured Output          │  {components, layout,
│                             │   colors, typography,
│                             │   tech_recommendations}
└──────────┬──────────────────┘
           ▼
┌─────────────────────────────┐
│  Agent Pipeline             │  架构师分解 → 代码生成
│  ArchitectAgent → CoderAgent│  视觉信息注入上下文
└─────────────────────────────┘
```

### 输入输出

**输入**：UI 截图（文件路径 `./screenshot.png` 或 base64 `data:image/png;base64,...`）

**输出**（JSON）：
```json
{
  "components": [
    {"type": "button", "text": "Get Started", "position": {"x": 500, "y": 550, "width": 200, "height": 50},
     "color": {"bg": "#007bff", "text": "#ffffff"}}
  ],
  "layout": {"type": "flex", "direction": "vertical", "description": "..."},
  "colors": {"primary": "#007bff", "background": "#ffffff", "palette": [...]},
  "typography": {"font_family": "system-ui", "heading_style": "bold, 32px"},
  "tech_recommendations": {"framework": "react", "styling": "tailwind", "layout_strategy": "flexbox"}
}
```

### Qwen-VL Prompt 设计

采用结构化 JSON Schema 约束输出，Prompt 包含：
1. 角色设定（UI/UX 分析专家）
2. 分析维度（组件、布局、配色、排版）
3. 严格 JSON Schema（20+ 组件类型、位置坐标、颜色值）
4. 技术推荐（框架、样式方案、布局策略）

### 性能优化

- **MD5 缓存**：相同图片命中时直接返回，避免重复 API 调用
- **三档预处理**：`fast`（仅缩放）、`standard`（+ 高斯去噪）、`detailed`（+ NLMeans 去噪）
- **JPEG 压缩**：预处理后编码为 JPEG 90% 质量，减少传输 Token

### 使用方式

```bash
# 设置 API Key
export DASHSCOPE_API_KEY=sk-your-key

# 运行 Demo
python demo_screenshot.py --image screenshot.png --instruction "用 React + Tailwind 实现"

# 在 Agent 中自动触发（CLI 模式）
python -m kiracode.cli.app
> 帮我根据 screenshot.png 实现这个界面
```

---

## Quick Start

```bash
# 1. 安装
pip install -e .

# 2. 运行完整演示
python demo.py

# 3. 启动交互式 CLI
python -m kiracode.cli.app
```

更多演示：
```bash
python demo_memory.py      # 记忆流转演示
python demo_context.py     # 上下文治理演示
python demo_full.py        # 全系统集成演示
python demo_screenshot.py  # 多模态截图分析演示（需 DASHSCOPE_API_KEY）
```

---

## 项目结构

```
kiracode/
├── kiracode/
│   ├── core/              # 核心引擎
│   │   ├── config.py      # Pydantic Settings + YAML + 环境变量
│   │   ├── event_bus.py   # 异步事件总线
│   │   └── token_budget.py # Token 预算分配与监控
│   ├── agents/            # Agent 层
│   │   ├── base.py        # Agent ABC + 状态机
│   │   └── architect.py   # Architect / Coder / Reviewer
│   ├── memory/            # 三层认知记忆
│   │   ├── working.py     # 工作记忆（会话上下文）
│   │   ├── episodic.py    # 情景记忆（任务轨迹）
│   │   ├── semantic.py    # 语义记忆（知识模式）
│   │   ├── graph.py       # 记忆图谱（NetworkX）
│   │   └── manager.py     # 统一管理器
│   ├── context/           # 上下文治理
│   │   ├── window.py      # 滑动窗口管理
│   │   └── compressor.py  # 智能压缩 + 引用追踪
│   ├── security/          # 安全基础设施
│   │   ├── sandbox.py     # 沙箱执行
│   │   ├── secrets_scanner.py # 密钥扫描
│   │   ├── audit_log.py   # 审计日志
│   │   └── rollback.py    # 操作回滚
│   ├── skills/            # 插件化 Skill 系统
│   │   ├── registry.py    # 注册中心
│   │   ├── loader.py      # 动态加载器
│   │   ├── router.py      # 语义路由
│   │   └── builtin/       # 内置 Skill（含 screenshot_analyze）
│   ├── models/            # 轻量视觉模型
│   │   └── ui_detector.py # YOLOv8-nano UI 元素检测
│   ├── cli/               # Rich CLI 交互界面
│   └── utils/             # 工具函数
├── tests/                 # 完整测试套件
├── docs/                  # 项目文档
├── configs/               # 配置文件模板
├── demo.py                # 完整流程演示
├── demo_full.py           # 全系统集成演示
├── demo_screenshot.py     # 多模态截图分析演示
└── pyproject.toml
```

---

## 演示效果

运行 `python demo_full.py` 的输出包含 8 个阶段：

1. **Core Engine** — 加载配置、初始化 EventBus 和 TokenBudget
2. **Skill System** — 加载 4 个内置 Skill，语义路由匹配
3. **Security** — 密钥扫描（检出 AWS Key / Token / DB URL）、沙箱执行、审计日志
4. **Memory** — 三层记忆写入 + consolidate 提炼语义模式
5. **Context** — 大文本自动压缩（7526 tokens → 208 tokens，97.2% 压缩率）
6. **Agents** — Architect 分解 4 个子任务，Coder 生成代码
7. **Budget** — Token 预算实时监控
8. **Summary** — 全系统状态一览表

---

## 技术栈

| 层 | 技术 |
|---|------|
| 数据校验 | Pydantic v2 + pydantic-settings |
| CLI | Rich + Click |
| 异步 | asyncio |
| 图谱 | NetworkX |
| 检索 | rank-bm25 + 伪向量嵌入 |
| 视觉 | OpenCV + Qwen-VL（百炼）+ YOLOv8-nano（可选） |
| Token | 自实现字符级计数器（可选 tiktoken） |
| 配置 | YAML + 环境变量覆盖 |
| 测试 | Pytest + pytest-asyncio |

---

## 文档索引

- [ARCHITECTURE.md](ARCHITECTURE.md) — 架构设计、Mermaid 图、ADR 决策记录
- [ENV.md](ENV.md) — 环境要求、安装步骤、Docker、配置说明
- [DEVELOPMENT.md](DEVELOPMENT.md) — 开发规范、测试、扩展指南、调试技巧

## License

MIT
