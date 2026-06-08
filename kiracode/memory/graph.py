"""Memory Graph — NetworkX-based relational memory structure.

Design decisions:
- Nodes represent memory entries (any layer: working/episodic/semantic).
- Edges represent typed relations: "triggers", "fixes", "depends_on", "similar_to".
- Supports add_node / add_edge / neighbors / find_path / subgraph operations.
- Node attributes store a reference (layer + entry_id) so the graph is a
  lightweight index, not a data store.
"""

from __future__ import annotations

from typing import Any

import networkx as nx
from pydantic import BaseModel, Field, PrivateAttr


class MemoryNode(BaseModel):
    node_id: str
    layer: str  # "working" | "episodic" | "semantic"
    entry_id: str  # id within the layer
    label: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryEdge(BaseModel):
    source_id: str
    target_id: str
    relation: str  # "triggers" | "fixes" | "depends_on" | "similar_to"
    weight: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryGraph(BaseModel):
    """Relational overlay on top of the three memory layers."""

    model_config = {"arbitrary_types_allowed": True}

    _graph: nx.DiGraph = PrivateAttr(default_factory=nx.DiGraph)

    # -- node operations ---------------------------------------------------

    def add_node(self, node: MemoryNode) -> None:
        self._graph.add_node(
            node.node_id,
            layer=node.layer,
            entry_id=node.entry_id,
            label=node.label,
            **node.metadata,
        )

    def remove_node(self, node_id: str) -> bool:
        if node_id in self._graph:
            self._graph.remove_node(node_id)
            return True
        return False

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        if node_id in self._graph:
            data = dict(self._graph.nodes[node_id])
            data["node_id"] = node_id
            return data
        return None

    # -- edge operations ---------------------------------------------------

    def add_edge(self, edge: MemoryEdge) -> None:
        self._graph.add_edge(
            edge.source_id,
            edge.target_id,
            relation=edge.relation,
            weight=edge.weight,
            **edge.metadata,
        )

    def remove_edge(self, source_id: str, target_id: str) -> bool:
        if self._graph.has_edge(source_id, target_id):
            self._graph.remove_edge(source_id, target_id)
            return True
        return False

    # -- query -------------------------------------------------------------

    def neighbors(
        self, node_id: str, relation: str | None = None
    ) -> list[str]:
        """Return neighbor node IDs, optionally filtered by edge relation."""
        if node_id not in self._graph:
            return []
        result = []
        for _, target, data in self._graph.out_edges(node_id, data=True):
            if relation is None or data.get("relation") == relation:
                result.append(target)
        return result

    def find_path(self, source_id: str, target_id: str) -> list[str] | None:
        try:
            return nx.shortest_path(self._graph, source_id, target_id)
        except (nx.NodeNotFound, nx.NetworkXNoPath):
            return None

    def get_edges(self, node_id: str) -> list[dict[str, Any]]:
        """Return all edges involving node_id."""
        edges = []
        for src, tgt, data in self._graph.out_edges(node_id, data=True):
            edges.append({"source": src, "target": tgt, **data})
        for src, tgt, data in self._graph.in_edges(node_id, data=True):
            edges.append({"source": src, "target": tgt, **data})
        return edges

    def subgraph(self, node_ids: list[str]) -> list[dict[str, Any]]:
        """Return edges within the induced subgraph."""
        sg = self._graph.subgraph(node_ids)
        return [
            {"source": s, "target": t, **d} for s, t, d in sg.edges(data=True)
        ]

    # -- stats -------------------------------------------------------------

    @property
    def node_count(self) -> int:
        return self._graph.number_of_nodes()

    @property
    def edge_count(self) -> int:
        return self._graph.number_of_edges()

    def summary(self) -> dict[str, Any]:
        rel_counts: dict[str, int] = {}
        for _, _, d in self._graph.edges(data=True):
            r = d.get("relation", "unknown")
            rel_counts[r] = rel_counts.get(r, 0) + 1
        return {
            "nodes": self.node_count,
            "edges": self.edge_count,
            "relations": rel_counts,
        }
