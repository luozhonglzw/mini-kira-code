"""LLM Integration Demo — Step 4: Provider abstraction + tiktoken.

Demonstrates:
1. LLM provider factory (mock, openai, anthropic)
2. Mock provider usage
3. Token counting (tiktoken + heuristic fallback)
4. Streaming responses
"""

from __future__ import annotations

import asyncio
import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

SEPARATOR = "=" * 72


async def demo_providers():
    """Demo: LLM provider abstraction."""
    print(SEPARATOR)
    print("LLM Provider Abstraction")
    print(SEPARATOR)

    from kiracode.llm import (
        LLMMessage, MessageRole, MockProvider, create_provider
    )

    # 1. Mock provider (no API key needed)
    print("\n[1] Mock Provider")
    provider = create_provider("mock", model="mock-model")
    messages = [
        LLMMessage(role=MessageRole.SYSTEM, content="You are a helpful assistant."),
        LLMMessage(role=MessageRole.USER, content="Explain what a REST API is."),
    ]

    response = await provider.chat(messages)
    print(f"  Model: {response.model}")
    print(f"  Provider: {response.provider}")
    print(f"  Content: {response.content[:100]}...")
    print(f"  Tokens: {response.usage}")

    # 2. Provider factory
    print("\n[2] Provider Factory")
    providers = ["mock", "openai", "anthropic"]
    for name in providers:
        try:
            p = create_provider(name, model="test-model")
            print(f"  {name}: {p.provider_name} ({p.model})")
        except ImportError as e:
            print(f"  {name}: requires additional dependencies")

    # 3. Multiple calls (call counter)
    print("\n[3] Multiple Calls (Mock Counter)")
    for i in range(3):
        resp = await provider.chat([LLMMessage(role=MessageRole.USER, content=f"Query {i}")])
    print(f"  Total calls: {provider.call_count}")

    # 4. Streaming
    print("\n[4] Streaming Response")
    stream_messages = [LLMMessage(role=MessageRole.USER, content="Count to 5")]
    print("  Stream: ", end="")
    async for chunk in provider.stream(stream_messages):
        print(chunk, end="")
    print()


def demo_token_counting():
    """Demo: Token counting with tiktoken and heuristic."""
    print(f"\n{SEPARATOR}")
    print("Token Counting")
    print(SEPARATOR)

    from kiracode.utils.token_counter import count_tokens, _heuristic_count

    test_texts = [
        "Hello, world!",
        "This is a longer sentence with more tokens to count.",
        "这是一个中文测试句子。",
        "Mixed English and 中文 content here.",
    ]

    print("\n[1] Heuristic (always available)")
    for text in test_texts:
        count = _heuristic_count(text)
        print(f"  [{count:3d} tokens] {text[:50]}")

    print("\n[2] With tiktoken (if installed)")
    try:
        import tiktoken
        print("  tiktoken is installed!")
        for text in test_texts:
            count = count_tokens(text, model="gpt-4o")
            print(f"  [{count:3d} tokens] {text[:50]}")
    except ImportError:
        print("  tiktoken not installed — using heuristic fallback")
        for text in test_texts:
            count = count_tokens(text)
            print(f"  [{count:3d} tokens] {text[:50]}")

    # 3. Token budget simulation
    print("\n[3] Token Budget Simulation")
    from kiracode.core.token_budget import TokenBudgetManager

    budget = TokenBudgetManager(total=1000)
    print(f"  Total budget: {budget.total}")
    print(f"  Remaining: {budget.total_remaining}")

    # Simulate consuming tokens
    for text in test_texts:
        tokens = _heuristic_count(text)
        allowed = budget.consume("agent", tokens)
        print(f"  Consumed {tokens} tokens — allowed: {allowed}")

    snapshot = budget.snapshot()
    print(f"  Final: used={snapshot.total_used}, remaining={snapshot.total_remaining}")


def demo_llm_config():
    """Demo: LLM configuration integration."""
    print(f"\n{SEPARATOR}")
    print("LLM Configuration")
    print(SEPARATOR)

    from kiracode.core.config import load_config

    config = load_config()
    print(f"\n  Provider: {config.llm.provider}")
    print(f"  Model: {config.llm.model}")
    print(f"  Temperature: {config.llm.temperature}")
    print(f"  Max tokens: {config.llm.max_tokens}")
    print(f"  Timeout: {config.llm.timeout}s")


async def main():
    print("KiraCode LLM Integration Demo")
    print("Step 4: Provider Abstraction + tiktoken\n")

    await demo_providers()
    demo_token_counting()
    demo_llm_config()

    print(f"\n{SEPARATOR}")
    print("LLM Integration Demo Complete!")
    print(SEPARATOR)


if __name__ == "__main__":
    asyncio.run(main())
