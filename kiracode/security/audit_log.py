"""Audit Log — structured JSONL logging for all security-relevant operations.

Design decisions:
- Append-only JSONL file for easy parsing and tailing.
- Each entry has: timestamp, event_type, actor, action, target, outcome, metadata.
- Thread-safe via asyncio lock.
- Supports querying by event_type, actor, time range.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AuditEntry(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: str  # "agent_action", "tool_call", "security_scan", "config_change"
    actor: str  # agent name or "user"
    action: str  # "execute_code", "read_file", "scan_secrets", etc.
    target: str = ""  # file path, command, etc.
    outcome: str = "success"  # success, failure, blocked
    details: dict[str, Any] = Field(default_factory=dict)
    risk_level: str = "low"  # low, medium, high, critical

    def to_jsonl(self) -> str:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False, default=str)


class AuditLog:
    """Append-only JSONL audit log."""

    def __init__(self, path: str = ".kiracode/audit/audit.jsonl") -> None:
        self._path = Path(path)
        self._lock = asyncio.Lock()
        self._entries: list[AuditEntry] = []

    async def log(self, entry: AuditEntry) -> None:
        """Append an entry to the audit log."""
        self._entries.append(entry)
        async with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(entry.to_jsonl() + "\n")

    async def log_event(
        self,
        event_type: str,
        actor: str,
        action: str,
        target: str = "",
        outcome: str = "success",
        details: dict[str, Any] | None = None,
        risk_level: str = "low",
    ) -> None:
        """Convenience: create and log an entry."""
        await self.log(
            AuditEntry(
                event_type=event_type,
                actor=actor,
                action=action,
                target=target,
                outcome=outcome,
                details=details or {},
                risk_level=risk_level,
            )
        )

    def query(
        self,
        event_type: str | None = None,
        actor: str | None = None,
        risk_level: str | None = None,
        limit: int = 50,
    ) -> list[AuditEntry]:
        """Query in-memory entries (current session only)."""
        results = self._entries
        if event_type:
            results = [e for e in results if e.event_type == event_type]
        if actor:
            results = [e for e in results if e.actor == actor]
        if risk_level:
            results = [e for e in results if e.risk_level == risk_level]
        return results[-limit:]

    def summary(self) -> dict[str, Any]:
        by_type: dict[str, int] = {}
        by_risk: dict[str, int] = {}
        for e in self._entries:
            by_type[e.event_type] = by_type.get(e.event_type, 0) + 1
            by_risk[e.risk_level] = by_risk.get(e.risk_level, 0) + 1
        return {
            "total_entries": len(self._entries),
            "by_type": by_type,
            "by_risk": by_risk,
            "log_path": str(self._path),
        }

    @property
    def entries(self) -> list[AuditEntry]:
        return list(self._entries)
