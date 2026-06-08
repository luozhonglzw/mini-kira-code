"""Token counter — supports tiktoken (accurate) or character-based heuristic (fallback).

When tiktoken is installed, uses the appropriate encoding for the model.
Otherwise falls back to a simple heuristic: 1 token ≈ 4 chars (English), 1 token ≈ 2 chars (CJK).
"""

from __future__ import annotations

from typing import Any


def _heuristic_count(text: str) -> int:
    """Character-based heuristic token count."""
    if not text:
        return 0
    cjk_chars = sum(1 for ch in text if "一" <= ch <= "鿿")
    ascii_chars = len(text) - cjk_chars
    return (ascii_chars // 4) + (cjk_chars // 2) + 1


def count_tokens(text: str, model: str = "") -> int:
    """Count tokens using tiktoken if available, otherwise heuristic.

    Args:
        text: Text to count tokens for.
        model: Model name for tiktoken encoding selection (e.g., "gpt-4o").

    Returns:
        Estimated token count.
    """
    if not text:
        return 0

    try:
        import tiktoken
        if model:
            try:
                encoding = tiktoken.encoding_for_model(model)
            except KeyError:
                encoding = tiktoken.get_encoding("cl100k_base")
        else:
            encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(text))
    except ImportError:
        return _heuristic_count(text)


def count_tokens_tiktoken(text: str, encoding_name: str = "cl100k_base") -> int:
    """Count tokens using a specific tiktoken encoding.

    Args:
        text: Text to count tokens for.
        encoding_name: tiktoken encoding name (cl100k_base, p50k_base, etc.)

    Returns:
        Token count.

    Raises:
        ImportError: If tiktoken is not installed.
    """
    import tiktoken
    encoding = tiktoken.get_encoding(encoding_name)
    return len(encoding.encode(text))


# Model to encoding mapping for common models
MODEL_ENCODINGS: dict[str, str] = {
    "gpt-4o": "o200k_base",
    "gpt-4-turbo": "cl100k_base",
    "gpt-4": "cl100k_base",
    "gpt-3.5-turbo": "cl100k_base",
    "claude": "cl100k_base",  # Approximate
    "default": "cl100k_base",
}
