"""Token Budget Manager — allocation, monitoring, and enforcement.

Design decisions:
- Central budget pool divided into allocations (agent, tool, system).
- Each allocation has a soft limit (warning) and hard limit (reject).
- Tracks usage per allocation with O(1) operations.
- Supports callbacks on threshold crossings (warning, hard_limit).
- Works with the EventBus to emit budget events.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Callable, Coroutine

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class BudgetLevel(str, Enum):
    NORMAL = "normal"
    WARNING = "warning"
    HARD_LIMIT = "hard_limit"
    EXCEEDED = "exceeded"


class Allocation(BaseModel):
    name: str
    limit: int  # max tokens for this allocation
    used: int = 0
    warning_threshold: float = 0.85
    hard_limit: float = 0.95

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    @property
    def utilization(self) -> float:
        return self.used / self.limit if self.limit else 0.0

    @property
    def level(self) -> BudgetLevel:
        ratio = self.utilization
        if ratio >= 1.0:
            return BudgetLevel.EXCEEDED
        if ratio >= self.hard_limit:
            return BudgetLevel.HARD_LIMIT
        if ratio >= self.warning_threshold:
            return BudgetLevel.WARNING
        return BudgetLevel.NORMAL


class BudgetSnapshot(BaseModel):
    """Point-in-time view of the budget."""
    allocations: dict[str, dict[str, Any]]
    total_limit: int
    total_used: int
    total_remaining: int
    overall_utilization: float


# Callback type: async def on_budget_event(allocation_name, level, snapshot)
BudgetCallback = Callable[[str, BudgetLevel, BudgetSnapshot], Coroutine[Any, Any, None]]


class TokenBudgetManager:
    """Manages token budget across multiple allocations."""

    def __init__(
        self,
        total: int = 128_000,
        warning_threshold: float = 0.85,
        hard_limit: float = 0.95,
    ) -> None:
        self._total = total
        self._warning_threshold = warning_threshold
        self._hard_limit = hard_limit
        self._allocations: dict[str, Allocation] = {}
        self._callbacks: list[BudgetCallback] = []
        self._previous_levels: dict[str, BudgetLevel] = {}

        # Create default allocations
        self.add_allocation("system", int(total * 0.05))
        self.add_allocation("agent", int(total * 0.45))
        self.add_allocation("tool", int(total * 0.30))
        self.add_allocation("reserve", int(total * 0.20))

    # -- allocation management --------------------------------------------

    def add_allocation(self, name: str, limit: int) -> Allocation:
        alloc = Allocation(
            name=name,
            limit=limit,
            warning_threshold=self._warning_threshold,
            hard_limit=self._hard_limit,
        )
        self._allocations[name] = alloc
        self._previous_levels[name] = BudgetLevel.NORMAL
        return alloc

    def get_allocation(self, name: str) -> Allocation | None:
        return self._allocations.get(name)

    def list_allocations(self) -> list[Allocation]:
        return list(self._allocations.values())

    # -- usage tracking ----------------------------------------------------

    def consume(self, allocation_name: str, tokens: int) -> bool:
        """Consume tokens from an allocation. Returns True if allowed."""
        alloc = self._allocations.get(allocation_name)
        if alloc is None:
            logger.warning("Unknown allocation: %s", allocation_name)
            return False

        if alloc.level == BudgetLevel.EXCEEDED:
            return False

        alloc.used += tokens

        # Check for level transitions and fire callbacks
        new_level = alloc.level
        old_level = self._previous_levels.get(allocation_name, BudgetLevel.NORMAL)
        if new_level != old_level:
            self._previous_levels[allocation_name] = new_level
            snapshot = self.snapshot()
            logger.info(
                "Budget level change: %s %s -> %s (utilization=%.1f%%)",
                allocation_name, old_level.value, new_level.value,
                alloc.utilization * 100,
            )
            self._fire_callbacks(allocation_name, new_level, snapshot)

        return True

    def release(self, allocation_name: str, tokens: int) -> None:
        """Return tokens to an allocation."""
        alloc = self._allocations.get(allocation_name)
        if alloc:
            alloc.used = max(0, alloc.used - tokens)

    def reset(self, allocation_name: str | None = None) -> None:
        """Reset usage for one or all allocations."""
        if allocation_name:
            alloc = self._allocations.get(allocation_name)
            if alloc:
                alloc.used = 0
                self._previous_levels[allocation_name] = BudgetLevel.NORMAL
        else:
            for alloc in self._allocations.values():
                alloc.used = 0
            self._previous_levels = {k: BudgetLevel.NORMAL for k in self._allocations}

    # -- callbacks ---------------------------------------------------------

    def on_budget_event(self, callback: BudgetCallback) -> None:
        self._callbacks.append(callback)

    def _fire_callbacks(self, name: str, level: BudgetLevel, snapshot: BudgetSnapshot) -> None:
        for cb in self._callbacks:
            try:
                # Schedule as task to avoid blocking
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(cb(name, level, snapshot))
                else:
                    loop.run_until_complete(cb(name, level, snapshot))
            except Exception:
                logger.exception("Budget callback failed")

    # -- snapshot ----------------------------------------------------------

    def snapshot(self) -> BudgetSnapshot:
        allocs = {}
        total_used = 0
        for name, a in self._allocations.items():
            allocs[name] = {
                "limit": a.limit,
                "used": a.used,
                "remaining": a.remaining,
                "utilization": round(a.utilization, 4),
                "level": a.level.value,
            }
            total_used += a.used
        return BudgetSnapshot(
            allocations=allocs,
            total_limit=self._total,
            total_used=total_used,
            total_remaining=max(0, self._total - total_used),
            overall_utilization=round(total_used / self._total, 4) if self._total else 0.0,
        )

    # -- convenience -------------------------------------------------------

    @property
    def total(self) -> int:
        return self._total

    @property
    def total_used(self) -> int:
        return sum(a.used for a in self._allocations.values())

    @property
    def total_remaining(self) -> int:
        return max(0, self._total - self.total_used)

    def summary(self) -> dict[str, Any]:
        s = self.snapshot()
        return {
            "total_limit": s.total_limit,
            "total_used": s.total_used,
            "total_remaining": s.total_remaining,
            "overall_utilization": s.overall_utilization,
            "allocations": s.allocations,
        }
