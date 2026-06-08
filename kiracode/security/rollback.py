"""Rollback — operation rollback via file snapshots.

Design decisions:
- Before any file-modifying operation, take a snapshot of affected files.
- If the operation fails or is rejected, restore from snapshot.
- Snapshots stored in memory (dict of filepath → content).
- For git-backed projects, could use git stash/reset instead.
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class Snapshot(BaseModel):
    snapshot_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    files: dict[str, str] = Field(default_factory=dict)  # filepath → original content
    metadata: dict[str, Any] = Field(default_factory=dict)


class RollbackManager:
    """Manages file snapshots for operation rollback."""

    def __init__(self) -> None:
        self._snapshots: dict[str, Snapshot] = {}
        self._counter = 0

    def take_snapshot(self, filepaths: list[str], label: str = "") -> str:
        """Snapshot the current state of files. Returns snapshot_id."""
        self._counter += 1
        sid = f"snap-{self._counter:04d}"
        files: dict[str, str] = {}

        for fp in filepaths:
            p = Path(fp)
            if p.exists() and p.is_file():
                try:
                    files[fp] = p.read_text(encoding="utf-8", errors="replace")
                except Exception as e:
                    logger.warning("Failed to snapshot %s: %s", fp, e)
            else:
                files[fp] = ""  # file doesn't exist yet

        snapshot = Snapshot(
            snapshot_id=sid,
            files=files,
            metadata={"label": label, "file_count": len(files)},
        )
        self._snapshots[sid] = snapshot
        logger.info("Snapshot %s taken: %d files", sid, len(files))
        return sid

    def rollback(self, snapshot_id: str) -> dict[str, Any]:
        """Restore files from a snapshot. Returns status dict."""
        snapshot = self._snapshots.get(snapshot_id)
        if snapshot is None:
            return {"success": False, "error": f"Snapshot {snapshot_id} not found"}

        restored = 0
        errors: list[str] = []
        for fp, original_content in snapshot.files.items():
            p = Path(fp)
            try:
                if original_content == "" and not p.exists():
                    continue  # nothing to restore
                if original_content == "":
                    # File was created after snapshot — delete it
                    if p.exists():
                        p.unlink()
                    restored += 1
                else:
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text(original_content, encoding="utf-8")
                    restored += 1
            except Exception as e:
                errors.append(f"{fp}: {e}")

        return {
            "success": len(errors) == 0,
            "snapshot_id": snapshot_id,
            "restored_files": restored,
            "errors": errors,
        }

    def discard_snapshot(self, snapshot_id: str) -> bool:
        return self._snapshots.pop(snapshot_id, None) is not None

    def list_snapshots(self) -> list[dict[str, Any]]:
        return [
            {
                "snapshot_id": s.snapshot_id,
                "created_at": s.created_at.isoformat(),
                "file_count": len(s.files),
                "label": s.metadata.get("label", ""),
            }
            for s in self._snapshots.values()
        ]

    def summary(self) -> dict[str, Any]:
        total_files = sum(len(s.files) for s in self._snapshots.values())
        return {
            "snapshot_count": len(self._snapshots),
            "total_files_tracked": total_files,
        }
