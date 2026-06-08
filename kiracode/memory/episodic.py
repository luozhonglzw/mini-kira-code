"""Episodic Memory — stores historical task execution traces.

Design decisions:
- TaskRecord is the atomic unit: captures full input/output/status of a task.
- In-memory list with optional JSONL persistence (Phase 2+).
- Retrieval by task_type, status, or keyword match on description.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class TaskRecord(BaseModel):
    task_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    task_type: str  # e.g. "code_generation", "review", "security_scan"
    description: str
    agent_name: str = ""
    input_data: dict[str, Any] = Field(default_factory=dict)
    output_data: dict[str, Any] = Field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING
    error_message: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None
    token_usage: int = 0
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def mark_running(self) -> None:
        self.status = TaskStatus.RUNNING
        self.started_at = datetime.now(timezone.utc)

    def mark_success(self, output: dict[str, Any] | None = None) -> None:
        self.status = TaskStatus.SUCCESS
        self.finished_at = datetime.now(timezone.utc)
        if output is not None:
            self.output_data = output

    def mark_failed(self, error: str) -> None:
        self.status = TaskStatus.FAILED
        self.finished_at = datetime.now(timezone.utc)
        self.error_message = error


class EpisodicMemory(BaseModel):
    """Historical task execution store."""

    records: list[TaskRecord] = Field(default_factory=list)
    max_entries: int = 1000

    # -- write -------------------------------------------------------------

    def store(self, record: TaskRecord) -> None:
        self.records.append(record)
        # evict oldest if over capacity
        if len(self.records) > self.max_entries:
            self.records = self.records[-self.max_entries:]

    # -- query -------------------------------------------------------------

    def query(
        self,
        task_type: str | None = None,
        status: TaskStatus | None = None,
        keyword: str | None = None,
        limit: int = 10,
    ) -> list[TaskRecord]:
        results = self.records
        if task_type is not None:
            results = [r for r in results if r.task_type == task_type]
        if status is not None:
            results = [r for r in results if r.status == status]
        if keyword is not None:
            kw = keyword.lower()
            results = [r for r in results if kw in r.description.lower()]
        return results[-limit:]

    def get_by_id(self, task_id: str) -> TaskRecord | None:
        for r in reversed(self.records):
            if r.task_id == task_id:
                return r
        return None

    def get_recent(self, n: int = 10) -> list[TaskRecord]:
        return self.records[-n:]

    def get_successful_patterns(self, task_type: str) -> list[TaskRecord]:
        """Return successful records for a given task type — useful for consolidation."""
        return [r for r in self.records if r.task_type == task_type and r.status == TaskStatus.SUCCESS]

    def summary(self) -> dict[str, Any]:
        by_type: dict[str, int] = {}
        by_status: dict[str, int] = {}
        for r in self.records:
            by_type[r.task_type] = by_type.get(r.task_type, 0) + 1
            by_status[r.status.value] = by_status.get(r.status.value, 0) + 1
        return {
            "total_records": len(self.records),
            "by_type": by_type,
            "by_status": by_status,
        }
