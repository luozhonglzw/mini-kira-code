"""Memory Manager — unified interface for the three-layer memory system.

Design decisions:
- Single entry point: remember() / recall() / consolidate().
- consolidate() extracts patterns from episodic memory and promotes them
  to semantic memory — this is the "sleep-time learning" analogue.
- Graph nodes are created automatically when memories are stored.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field

from kiracode.memory.episodic import EpisodicMemory, TaskRecord
from kiracode.memory.graph import MemoryEdge, MemoryGraph, MemoryNode
from kiracode.memory.semantic import KnowledgeEntry, SemanticMemory
from kiracode.memory.working import Message, WorkingMemory


class MemoryManager(BaseModel):
    """Unified facade over working / episodic / semantic memory + graph."""

    working: WorkingMemory = Field(default_factory=WorkingMemory)
    episodic: EpisodicMemory = Field(default_factory=EpisodicMemory)
    semantic: SemanticMemory = Field(default_factory=SemanticMemory)
    graph: MemoryGraph = Field(default_factory=MemoryGraph)

    model_config = {"arbitrary_types_allowed": True}

    # ------------------------------------------------------------------
    # remember — store data into the appropriate layer
    # ------------------------------------------------------------------

    def remember_message(self, message: Message) -> str:
        """Push a message to working memory. Returns graph node id."""
        self.working.push(message)
        node_id = f"wm-{uuid.uuid4().hex[:8]}"
        self.graph.add_node(
            MemoryNode(
                node_id=node_id,
                layer="working",
                entry_id=str(len(self.working.messages) - 1),
                label=message.content[:60],
            )
        )
        return node_id

    def remember_task(self, record: TaskRecord) -> str:
        """Store a completed task in episodic memory. Returns graph node id."""
        self.episodic.store(record)
        node_id = f"ep-{record.task_id}"
        self.graph.add_node(
            MemoryNode(
                node_id=node_id,
                layer="episodic",
                entry_id=record.task_id,
                label=record.description[:60],
            )
        )
        return node_id

    def remember_knowledge(self, entry: KnowledgeEntry) -> str:
        """Store a knowledge pattern in semantic memory. Returns graph node id."""
        self.semantic.add(entry)
        node_id = f"sem-{entry.entry_id}"
        self.graph.add_node(
            MemoryNode(
                node_id=node_id,
                layer="semantic",
                entry_id=entry.entry_id,
                label=entry.title[:60],
            )
        )
        return node_id

    # ------------------------------------------------------------------
    # recall — retrieve from any layer
    # ------------------------------------------------------------------

    def recall(
        self,
        query: str,
        memory_type: str = "semantic",
        top_k: int = 5,
    ) -> list[Any]:
        """Retrieve memories matching query.

        memory_type: "working" | "episodic" | "semantic"
        """
        if memory_type == "working":
            # keyword search in working memory
            kw = query.lower()
            return [
                m for m in self.working.messages if kw in m.content.lower()
            ][:top_k]
        elif memory_type == "episodic":
            return self.episodic.query(keyword=query, limit=top_k)
        elif memory_type == "semantic":
            return self.semantic.search(query, top_k=top_k)
        else:
            raise ValueError(f"Unknown memory_type: {memory_type}")

    # ------------------------------------------------------------------
    # consolidate — promote working → episodic / semantic
    # ------------------------------------------------------------------

    def consolidate(self) -> dict[str, Any]:
        """Extract patterns from episodic memory and promote to semantic.

        Strategy:
        1. Group successful episodic records by task_type.
        2. For each group with >= 2 successes, extract a CodePattern.
        3. Link the new semantic node to its source episodic nodes.
        """
        promoted = 0
        new_entries: list[str] = []

        # group successful records by task_type
        type_groups: dict[str, list[TaskRecord]] = {}
        for rec in self.episodic.records:
            if rec.status.value == "success":
                type_groups.setdefault(rec.task_type, []).append(rec)

        for task_type, records in type_groups.items():
            if len(records) < 1:
                continue

            # Extract a pattern from the descriptions
            descriptions = [r.description for r in records]
            outputs = [str(r.output_data) for r in records]

            pattern_title = f"Pattern: {task_type} (from {len(records)} tasks)"
            pattern_content = (
                f"Observed {len(records)} successful executions of '{task_type}'.\n"
                f"Common descriptions: {'; '.join(descriptions[:5])}\n"
                f"Typical output keys: {list(records[0].output_data.keys()) if records[0].output_data else 'N/A'}"
            )

            entry = KnowledgeEntry(
                title=pattern_title,
                content=pattern_content,
                category="code_pattern",
                source_task_id=records[0].task_id,
                confidence=min(1.0, len(records) * 0.3),
            )
            sem_node_id = self.remember_knowledge(entry)
            promoted += 1
            new_entries.append(sem_node_id)

            # Link semantic node → source episodic nodes
            for rec in records:
                ep_node_id = f"ep-{rec.task_id}"
                if self.graph.get_node(ep_node_id):
                    self.graph.add_edge(
                        MemoryEdge(
                            source_id=sem_node_id,
                            target_id=ep_node_id,
                            relation="derived_from",
                        )
                    )

        return {
            "promoted_patterns": promoted,
            "new_semantic_node_ids": new_entries,
            "episodic_count": len(self.episodic.records),
            "semantic_count": len(self.semantic.entries),
            "graph_summary": self.graph.summary(),
        }

    # ------------------------------------------------------------------
    # summary
    # ------------------------------------------------------------------

    def full_summary(self) -> dict[str, Any]:
        return {
            "working_memory": self.working.summary(),
            "episodic_memory": self.episodic.summary(),
            "semantic_memory": self.semantic.summary(),
            "graph": self.graph.summary(),
        }
