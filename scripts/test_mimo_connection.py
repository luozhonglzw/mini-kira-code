"""MiMo API connectivity test (standalone, no pytest required).

Usage:
    export MIMO_API_KEY=tp-your-key-here
    python scripts/test_mimo_connection.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

# Force UTF-8 on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def main() -> None:
    api_key = os.environ.get("MIMO_API_KEY", "")
    if not api_key:
        print("[ERROR] MIMO_API_KEY not set.")
        print("  export MIMO_API_KEY=tp-your-key-here")
        sys.exit(1)

    print("=" * 60)
    print("MiMo API Connection Test")
    print("=" * 60)
    print(f"  Base URL: https://token-plan-cn.xiaomimimo.com/v1")
    print(f"  Model:    mimo-v2.5-pro")
    print(f"  API Key:  {api_key[:6]}...{api_key[-4:]}")
    print()

    from kiracode.llm.mimo_provider import MimoProvider
    from kiracode.llm.base import LLMMessage, MessageRole

    provider = MimoProvider(api_key=api_key, model="mimo-v2.5-pro")
    messages = [LLMMessage(role=MessageRole.USER, content="Hello, are you MiMo? Reply briefly.")]

    print("[1] Sending request...")
    start = time.time()
    try:
        response = await provider.chat(messages, max_tokens=100)
        elapsed = time.time() - start

        print(f"[OK] Response received in {elapsed:.2f}s")
        print(f"  Content: {response.content[:200]}")
        print(f"  Model: {response.model}")
        print(f"  Finish: {response.finish_reason}")
        print(f"  Tokens: prompt={response.usage.get('prompt_tokens', 0)}, "
              f"completion={response.usage.get('completion_tokens', 0)}, "
              f"total={response.total_tokens}")

        if response.reasoning_content:
            print(f"  Reasoning: {response.reasoning_content[:100]}...")
        else:
            print(f"  Reasoning: (none, thinking mode disabled)")

    except ValueError as e:
        print(f"[FAIL] 400 Bad Request: {e}")
    except RuntimeError as e:
        print(f"[FAIL] 429 Rate Limited: {e}")
        print("  Wait a moment and try again.")
    except ConnectionError as e:
        print(f"[FAIL] 502 Gateway Error: {e}")
        print("  MiMo API may be temporarily unavailable.")
    except Exception as e:
        print(f"[FAIL] Unexpected error: {type(e).__name__}: {e}")

    print()
    print("=" * 60)
    print("Test complete.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
