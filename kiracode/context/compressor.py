"""Smart Context Compressor — shrinks large tool outputs with reference tracking.

Design decisions:
- Tool results > 2000 tokens are compressed into structured summaries.
- Original content is stored in a reference table keyed by ref_id.
- The summary preserves: key data points, file paths, error messages,
  and a pointer to the original content for on-demand retrieval.
- Compression ratio is tracked for observability.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from typing import Any

from pydantic import BaseModel, Field, PrivateAttr

from kiracode.memory.working import Message
from kiracode.utils.token_counter import count_tokens


class CompressedContext(BaseModel):
    ref_id: str
    summary: str
    original_token_count: int
    compressed_token_count: int
    compression_ratio: float  # compressed / original
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompressorConfig(BaseModel):
    threshold_tokens: int = 2000  # compress anything above this
    target_ratio: float = 0.3  # aim for 30% of original size
    max_summary_tokens: int = 500  # cap summary length


class ReferenceStore(BaseModel):
    """Stores original content for on-demand retrieval."""

    model_config = {"arbitrary_types_allowed": True}

    _refs: dict[str, str] = PrivateAttr(default_factory=dict)

    def store(self, ref_id: str, content: str) -> None:
        self._refs[ref_id] = content

    def resolve(self, ref_id: str) -> str | None:
        return self._refs.get(ref_id)

    def remove(self, ref_id: str) -> bool:
        return self._refs.pop(ref_id, None) is not None

    def count(self) -> int:
        return len(self._refs)

    def clear(self) -> None:
        self._refs.clear()


class SmartCompressor(BaseModel):
    """Compresses large context messages while preserving key information.

    Works with WindowManager: the window calls compress() on oversized
    tool messages, and stores the ref_id in message metadata so the
    original can be retrieved later via resolve_reference().
    """

    config: CompressorConfig = Field(default_factory=CompressorConfig)
    store: ReferenceStore = Field(default_factory=ReferenceStore)

    model_config = {"arbitrary_types_allowed": True}

    _stats_compressed: int = PrivateAttr(default=0)
    _stats_saved_tokens: int = PrivateAttr(default=0)

    # -- public API --------------------------------------------------------

    def compress(self, message: Message) -> CompressedContext:
        """Compress a message's content. Returns CompressedContext with ref_id."""
        original = message.content
        original_tokens = count_tokens(original)

        if original_tokens <= self.config.threshold_tokens:
            # No compression needed
            return CompressedContext(
                ref_id="",
                summary=original,
                original_token_count=original_tokens,
                compressed_token_count=original_tokens,
                compression_ratio=1.0,
            )

        # Generate ref_id and store original
        ref_id = f"ref-{uuid.uuid4().hex[:10]}"
        self.store.store(ref_id, original)

        # Extract structured summary
        summary = self._extract_summary(original, ref_id)
        compressed_tokens = count_tokens(summary)

        self._stats_compressed += 1
        self._stats_saved_tokens += original_tokens - compressed_tokens

        return CompressedContext(
            ref_id=ref_id,
            summary=summary,
            original_token_count=original_tokens,
            compressed_token_count=compressed_tokens,
            compression_ratio=round(compressed_tokens / original_tokens, 3),
            metadata={"message_role": message.role.value},
        )

    def resolve_reference(self, ref_id: str) -> str | None:
        """Retrieve original content by ref_id."""
        return self.store.resolve(ref_id)

    # -- summary extraction ------------------------------------------------

    def _extract_summary(self, content: str, ref_id: str) -> str:
        """Extract a structured summary from large content.

        Strategy:
        1. Try JSON parsing → extract top-level keys and first few items.
        2. Try log parsing → extract errors, warnings, key lines.
        3. Fallback → first N lines + last N lines + line count.
        """
        # Attempt JSON
        try:
            data = json.loads(content)
            return self._summarize_json(data, ref_id)
        except (json.JSONDecodeError, TypeError):
            pass

        # Attempt structured text / log
        lines = content.split("\n")
        if len(lines) > 20:
            return self._summarize_lines(lines, ref_id)

        # Short content — return as-is
        return content

    def _summarize_json(self, data: Any, ref_id: str) -> str:
        """Summarize JSON data: show structure + sample values."""
        if isinstance(data, dict):
            keys = list(data.keys())
            sample: dict[str, Any] = {}
            for k in keys[:10]:
                v = data[k]
                if isinstance(v, (str, int, float, bool)):
                    sample[k] = v
                elif isinstance(v, list):
                    sample[k] = f"[list, {len(v)} items]"
                elif isinstance(v, dict):
                    sample[k] = f"{{dict, {len(v)} keys}}"
                else:
                    sample[k] = str(type(v).__name__)
            return (
                f"[Compressed JSON — {len(keys)} top-level keys, ref={ref_id}]\n"
                f"Keys: {keys[:10]}{'...' if len(keys) > 10 else ''}\n"
                f"Sample: {json.dumps(sample, ensure_ascii=False, default=str)}"
            )
        elif isinstance(data, list):
            return (
                f"[Compressed JSON array — {len(data)} items, ref={ref_id}]\n"
                f"First item: {json.dumps(data[0], ensure_ascii=False, default=str)[:200] if data else '(empty)'}"
            )
        return f"[Compressed JSON — ref={ref_id}]\n{str(data)[:300]}"

    def _summarize_lines(self, lines: list[str], ref_id: str) -> str:
        """Summarize line-based content: errors first, then head/tail."""
        errors = [l for l in lines if re.search(r"(?i)(error|exception|traceback|fatal)", l)]
        warnings = [l for l in lines if re.search(r"(?i)(warn|warning)", l)]

        head = lines[:5]
        tail = lines[-3:]

        parts = [f"[Compressed log — {len(lines)} lines, ref={ref_id}]"]
        if errors:
            parts.append(f"Errors ({len(errors)}):")
            parts.extend(f"  {e[:150]}" for e in errors[:3])
        if warnings:
            parts.append(f"Warnings ({len(warnings)}):")
            parts.extend(f"  {w[:150]}" for w in warnings[:2])
        parts.append(f"Head: {' | '.join(l.strip()[:80] for l in head)}")
        parts.append(f"Tail: {' | '.join(l.strip()[:80] for l in tail)}")
        return "\n".join(parts)

    # -- stats -------------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        return {
            "compressed_count": self._stats_compressed,
            "saved_tokens": self._stats_saved_tokens,
            "stored_references": self.store.count(),
        }
