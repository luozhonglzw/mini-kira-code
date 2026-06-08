"""Configuration — Pydantic Settings with YAML + environment variable loading.

Design decisions:
- Uses pydantic-settings BaseSettings for env var support (KIRACODE_* prefix).
- YAML file is loaded first, then env vars override.
- Nested models for each subsystem (llm, agents, memory, etc.).
- Immutable after creation (frozen=True on sub-models).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


# ── sub-configs ────────────────────────────────────────────────────────────


class LLMConfig(BaseModel):
    provider: str = "mimo"
    model: str = "mimo-v2.5-pro"
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: int = 300
    # DashScope (阿里云百炼) config
    dashscope_api_key: str = ""
    dashscope_model: str = "qwen-max"
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    # MiMo-specific config
    mimo_api_key: str = ""
    mimo_model: str = "mimo-v2.5-pro"
    mimo_base_url: str = "https://token-plan-cn.xiaomimimo.com/anthropic"
    mimo_thinking_mode: bool = False


class AgentConfig(BaseModel):
    enabled: bool = True
    max_subtasks: int = 10
    planning_strategy: str = "decompose"
    max_retries: int = 3
    sandbox_enabled: bool = True
    strict_mode: bool = False
    scan_secrets: bool = True
    scan_sast: bool = True


class AgentsConfig(BaseModel):
    architect: AgentConfig = Field(default_factory=AgentConfig)
    coder: AgentConfig = Field(default_factory=lambda: AgentConfig(max_retries=3))
    reviewer: AgentConfig = Field(default_factory=lambda: AgentConfig(strict_mode=False))
    security_auditor: AgentConfig = Field(
        default_factory=lambda: AgentConfig(scan_secrets=True, scan_sast=True)
    )


class WorkingMemoryConfig(BaseModel):
    max_items: int = 50
    ttl_seconds: int = 3600


class EpisodicMemoryConfig(BaseModel):
    max_entries: int = 1000
    persistence_path: str = ".kiracode/memory/episodic.jsonl"


class SemanticMemoryConfig(BaseModel):
    embedding_dim: int = 384
    persistence_path: str = ".kiracode/memory/semantic.index"


class GraphConfig(BaseModel):
    enabled: bool = True
    max_nodes: int = 5000


class MemoryConfig(BaseModel):
    working_memory: WorkingMemoryConfig = Field(default_factory=WorkingMemoryConfig)
    episodic_memory: EpisodicMemoryConfig = Field(default_factory=EpisodicMemoryConfig)
    semantic_memory: SemanticMemoryConfig = Field(default_factory=SemanticMemoryConfig)
    graph: GraphConfig = Field(default_factory=GraphConfig)


class ContextConfig(BaseModel):
    max_tokens: int = 128000
    reserve_tokens: int = 4096
    compression_threshold: float = 0.8
    strategy: str = "sliding_window"


class TokenBudgetConfig(BaseModel):
    total: int = 128000
    agent_reserve: int = 8192
    tool_reserve: int = 16384
    warning_threshold: float = 0.85
    hard_limit: float = 0.95


class SandboxConfig(BaseModel):
    enabled: bool = True
    timeout: int = 30
    max_memory_mb: int = 512


class SecretsScannerConfig(BaseModel):
    enabled: bool = True
    entropy_threshold: float = 4.5


class AuditLogConfig(BaseModel):
    enabled: bool = True
    path: str = ".kiracode/audit/audit.jsonl"


class RollbackConfig(BaseModel):
    enabled: bool = True
    strategy: str = "git"


class SecurityConfig(BaseModel):
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    secrets_scanner: SecretsScannerConfig = Field(default_factory=SecretsScannerConfig)
    audit_log: AuditLogConfig = Field(default_factory=AuditLogConfig)
    rollback: RollbackConfig = Field(default_factory=RollbackConfig)


class SkillsRAGConfig(BaseModel):
    enabled: bool = True
    top_k: int = 5
    score_threshold: float = 0.6


class SkillsConfig(BaseModel):
    auto_discover: bool = True
    directories: list[str] = Field(
        default_factory=lambda: ["kiracode/skills/builtin", ".kiracode/skills"]
    )
    rag: SkillsRAGConfig = Field(default_factory=SkillsRAGConfig)


class CLIConfig(BaseModel):
    theme: str = "dark"
    show_token_usage: bool = True
    show_agent_state: bool = True


class QwenVLConfig(BaseModel):
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model: str = "qwen-vl-max"
    max_tokens: int = 4096
    temperature: float = 0.1


class YOLOConfig(BaseModel):
    enabled: bool = False
    model_path: str = "yolov8n.pt"
    confidence: float = 0.35
    device: str = "cpu"


class PreprocessingConfig(BaseModel):
    max_dimension: int = 1024
    default_detail_level: str = "standard"
    jpeg_quality: int = 90


class VisionConfig(BaseModel):
    qwen_vl: QwenVLConfig = Field(default_factory=QwenVLConfig)
    yolo: YOLOConfig = Field(default_factory=YOLOConfig)
    preprocessing: PreprocessingConfig = Field(default_factory=PreprocessingConfig)


class AppConfig(BaseModel):
    name: str = "KiraCode"
    version: str = "0.1.0"
    log_level: str = "INFO"
    log_format: str = "json"


# ── root config ────────────────────────────────────────────────────────────


class KiraConfig(BaseSettings):
    """Root configuration — loads from YAML file then env vars override."""

    app: AppConfig = Field(default_factory=AppConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    agents: AgentsConfig = Field(default_factory=AgentsConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    context: ContextConfig = Field(default_factory=ContextConfig)
    token_budget: TokenBudgetConfig = Field(default_factory=TokenBudgetConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    vision: VisionConfig = Field(default_factory=VisionConfig)
    cli: CLIConfig = Field(default_factory=CLIConfig)

    model_config = {
        "env_prefix": "KIRACODE_",
        "env_nested_delimiter": "__",
    }


def load_config(path: str | Path | None = None) -> KiraConfig:
    """Load config from YAML file, then overlay env vars.

    Args:
        path: Path to YAML config file. Defaults to configs/default.yaml
              relative to the project root.
    """
    if path is None:
        # Walk up to find configs/default.yaml
        candidates = [
            Path.cwd() / "configs" / "default.yaml",
            Path(__file__).parent.parent.parent / "configs" / "default.yaml",
        ]
        for p in candidates:
            if p.exists():
                path = p
                break

    data: dict[str, Any] = {}
    if path is not None:
        p = Path(path)
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

    # KiraConfig will also read env vars automatically
    return KiraConfig(**data)
