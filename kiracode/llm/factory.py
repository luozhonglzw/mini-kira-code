"""LLM Provider Factory — creates providers based on configuration.

Usage:
    from kiracode.llm.factory import create_provider
    provider = create_provider(provider="mimo", model="mimo-v2.5-pro")
"""

from __future__ import annotations

import os
from typing import Any

from kiracode.llm.base import LLMProvider
from kiracode.llm.mock_provider import MockProvider


def create_provider(
    provider: str = "mock",
    model: str = "",
    **kwargs: Any,
) -> LLMProvider:
    """Create an LLM provider instance.

    Args:
        provider: Provider name ("openai", "anthropic", "mimo", "mock").
        model: Model identifier. Uses provider default if empty.
        **kwargs: Additional provider-specific arguments (api_key, base_url, etc.).

    Returns:
        LLMProvider instance.

    Raises:
        ValueError: If provider is unknown.
        ImportError: If provider dependencies are not installed.
    """
    provider_lower = provider.lower()

    if provider_lower == "mock":
        return MockProvider(model=model or "mock-model", **kwargs)

    elif provider_lower == "openai":
        from kiracode.llm.openai_provider import OpenAIProvider
        return OpenAIProvider(model=model or "gpt-4o", **kwargs)

    elif provider_lower == "anthropic":
        from kiracode.llm.anthropic_provider import AnthropicProvider
        return AnthropicProvider(model=model or "claude-sonnet-4-20250514", **kwargs)

    elif provider_lower == "mimo":
        from kiracode.llm.mimo_provider import MimoProvider
        return MimoProvider(
            api_key=kwargs.pop("api_key", None) or os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("MIMO_API_KEY"),
            model=model or "mimo-v2.5-pro",
            base_url=kwargs.pop("base_url", os.environ.get("ANTHROPIC_BASE_URL", "https://token-plan-cn.xiaomimimo.com/anthropic")),
            timeout=kwargs.pop("timeout", 300),
            **kwargs,
        )

    elif provider_lower == "dashscope":
        from kiracode.llm.dashscope_provider import DashScopeProvider
        return DashScopeProvider(
            api_key=kwargs.pop("api_key", None) or os.environ.get("DASHSCOPE_API_KEY"),
            model=model or "qwen-max",
            base_url=kwargs.pop("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            timeout=kwargs.pop("timeout", 60),
            **kwargs,
        )

    else:
        raise ValueError(
            f"Unknown LLM provider: '{provider}'. "
            f"Available: mock, openai, anthropic, mimo, dashscope"
        )
