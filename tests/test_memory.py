"""Tests for the three-layer memory system."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kiracode.memory.episodic import EpisodicMemory, TaskRecord, TaskStatus
from kiracode.memory.graph import MemoryEdge, MemoryGraph, MemoryNode
from kiracode.memory.manager import MemoryManager
from kiracode.memory.semantic import KnowledgeEntry, SemanticMemory
from kiracode.memory.working import Message, MessageRole, WorkingMemory


# ── Working Memory Tests ───────────────────────────────────────────────────


@pytest.mark.unit
class TestWorkingMemory:
    def test_push_and_count(self):
        wm = WorkingMemory(max_tokens=1000)
        wm.push(Message(role=MessageRole.USER, content="hello"))
        assert len(wm.messages) == 1
        assert wm.total_tokens > 0

    def test_pop(self):
        wm = WorkingMemory(max_tokens=1000)
        wm.push(Message(role=MessageRole.USER, content="hello"))
        wm.push(Message(role=MessageRole.ASSISTANT, content="world"))
        msg = wm.pop()
        assert msg is not None
        assert msg.role == MessageRole.ASSISTANT
        assert len(wm.messages) == 1

    def test_pop_empty(self):
        wm = WorkingMemory(max_tokens=1000)
        assert wm.pop() is None

    def test_truncate_to_budget(self):
        wm = WorkingMemory(max_tokens=1000)
        for i in range(20):
            wm.push(Message(role=MessageRole.USER, content=f"message {i} " * 10))
        initial_count = len(wm.messages)
        evicted = wm.truncate_to_budget(200)
        assert len(evicted) > 0
        assert wm.total_tokens <= 200 or len(wm.messages) <= 1

    def test_remaining_tokens(self):
        wm = WorkingMemory(max_tokens=100)
        assert wm.remaining_tokens == 100
        wm.push(Message(role=MessageRole.USER, content="hello"))
        assert wm.remaining_tokens < 100

    def test_context_messages(self):
        wm = WorkingMemory(max_tokens=1000)
        wm.push(Message(role=MessageRole.USER, content="hello"))
        ctx = wm.get_context_messages()
        assert len(ctx) == 1
        assert ctx[0]["role"] == "user"
        assert ctx[0]["content"] == "hello"

    def test_summary(self):
        wm = WorkingMemory(max_tokens=1000)
        wm.push(Message(role=MessageRole.USER, content="test"))
        s = wm.summary()
        assert s["message_count"] == 1
        assert s["total_tokens"] > 0
        assert "utilization" in s


# ── Episodic Memory Tests ──────────────────────────────────────────────────


@pytest.mark.unit
class TestEpisodicMemory:
    def test_store_and_query(self):
        em = EpisodicMemory()
        rec = TaskRecord(task_type="code_gen", description="Generate login", agent_name="coder")
        rec.mark_success(output={"code": "def login(): pass"})
        em.store(rec)

        results = em.query(task_type="code_gen")
        assert len(results) == 1
        assert results[0].task_type == "code_gen"

    def test_query_by_status(self):
        em = EpisodicMemory()
        r1 = TaskRecord(task_type="gen", description="task 1")
        r1.mark_success()
        r2 = TaskRecord(task_type="gen", description="task 2")
        r2.mark_failed("error")
        em.store(r1)
        em.store(r2)

        assert len(em.query(status=TaskStatus.SUCCESS)) == 1
        assert len(em.query(status=TaskStatus.FAILED)) == 1

    def test_query_by_keyword(self):
        em = EpisodicMemory()
        r = TaskRecord(task_type="review", description="Security audit for login module")
        r.mark_success()
        em.store(r)

        assert len(em.query(keyword="security")) == 1
        assert len(em.query(keyword="nonexistent")) == 0

    def test_get_by_id(self):
        em = EpisodicMemory()
        r = TaskRecord(task_id="t-001", task_type="gen", description="test")
        r.mark_success()
        em.store(r)

        found = em.get_by_id("t-001")
        assert found is not None
        assert found.task_id == "t-001"
        assert em.get_by_id("nonexistent") is None

    def test_max_entries_eviction(self):
        em = EpisodicMemory(max_entries=5)
        for i in range(10):
            r = TaskRecord(task_type="gen", description=f"task {i}")
            r.mark_success()
            em.store(r)
        assert len(em.records) == 5
        assert em.records[0].description == "task 5"

    def test_summary(self):
        em = EpisodicMemory()
        r = TaskRecord(task_type="gen", description="test")
        r.mark_success()
        em.store(r)
        s = em.summary()
        assert s["total_records"] == 1
        assert s["by_type"]["gen"] == 1


# ── Semantic Memory Tests ──────────────────────────────────────────────────


@pytest.mark.unit
class TestSemanticMemory:
    def test_add_and_search(self):
        sm = SemanticMemory()
        sm.add(KnowledgeEntry(title="Auth pattern", content="Always hash passwords", category="security"))
        sm.add(KnowledgeEntry(title="REST pattern", content="Use proper HTTP methods", category="best_practice"))

        results = sm.search("password hashing", top_k=2)
        assert len(results) > 0
        # Auth pattern should be closer
        assert results[0][0].title == "Auth pattern"

    def test_search_by_category(self):
        sm = SemanticMemory()
        sm.add(KnowledgeEntry(title="A", content="security stuff", category="security"))
        sm.add(KnowledgeEntry(title="B", content="code pattern", category="code_pattern"))

        results = sm.search("security", category="security", top_k=5)
        assert len(results) == 1
        assert results[0][0].category == "security"

    def test_remove(self):
        sm = SemanticMemory()
        entry = KnowledgeEntry(title="test", content="test content")
        sm.add(entry)
        assert sm.remove(entry.entry_id) is True
        assert len(sm.entries) == 0
        assert sm.remove("nonexistent") is False

    def test_summary(self):
        sm = SemanticMemory()
        sm.add(KnowledgeEntry(title="A", content="a", category="security"))
        sm.add(KnowledgeEntry(title="B", content="b", category="security"))
        s = sm.summary()
        assert s["total_entries"] == 2
        assert s["by_category"]["security"] == 2


# ── Memory Graph Tests ─────────────────────────────────────────────────────


@pytest.mark.unit
class TestMemoryGraph:
    def test_add_and_get_node(self):
        g = MemoryGraph()
        g.add_node(MemoryNode(node_id="n1", layer="episodic", entry_id="e1", label="test"))
        node = g.get_node("n1")
        assert node is not None
        assert node["layer"] == "episodic"

    def test_add_edge_and_neighbors(self):
        g = MemoryGraph()
        g.add_node(MemoryNode(node_id="n1", layer="episodic", entry_id="e1"))
        g.add_node(MemoryNode(node_id="n2", layer="semantic", entry_id="s1"))
        g.add_edge(MemoryEdge(source_id="n1", target_id="n2", relation="derived_from"))

        neighbors = g.neighbors("n1")
        assert "n2" in neighbors

        filtered = g.neighbors("n1", relation="other")
        assert len(filtered) == 0

    def test_find_path(self):
        g = MemoryGraph()
        g.add_node(MemoryNode(node_id="a", layer="ep", entry_id="1"))
        g.add_node(MemoryNode(node_id="b", layer="ep", entry_id="2"))
        g.add_node(MemoryNode(node_id="c", layer="sem", entry_id="3"))
        g.add_edge(MemoryEdge(source_id="a", target_id="b", relation="triggers"))
        g.add_edge(MemoryEdge(source_id="b", target_id="c", relation="derived_from"))

        path = g.find_path("a", "c")
        assert path == ["a", "b", "c"]
        assert g.find_path("c", "a") is None

    def test_remove_node(self):
        g = MemoryGraph()
        g.add_node(MemoryNode(node_id="n1", layer="ep", entry_id="1"))
        assert g.remove_node("n1") is True
        assert g.get_node("n1") is None
        assert g.remove_node("n1") is False

    def test_summary(self):
        g = MemoryGraph()
        g.add_node(MemoryNode(node_id="n1", layer="ep", entry_id="1"))
        g.add_node(MemoryNode(node_id="n2", layer="sem", entry_id="2"))
        g.add_edge(MemoryEdge(source_id="n1", target_id="n2", relation="fixes"))
        s = g.summary()
        assert s["nodes"] == 2
        assert s["edges"] == 1
        assert s["relations"]["fixes"] == 1


# ── MemoryManager Tests ────────────────────────────────────────────────────


@pytest.mark.unit
class TestMemoryManager:
    def test_remember_and_recall(self):
        mgr = MemoryManager()
        mgr.remember_message(Message(role=MessageRole.USER, content="Build a REST API"))
        mgr.remember_message(Message(role=MessageRole.ASSISTANT, content="Plan: 3 steps"))

        results = mgr.recall("REST", memory_type="working")
        assert len(results) == 1

    def test_consolidate(self):
        mgr = MemoryManager()
        for i in range(3):
            rec = TaskRecord(task_type="code_gen", description=f"Generate login variant {i}")
            rec.mark_success(output={"code": f"def login_{i}(): pass"})
            mgr.remember_task(rec)

        result = mgr.consolidate()
        assert result["promoted_patterns"] >= 1
        assert len(mgr.semantic.entries) >= 1

    def test_full_summary(self):
        mgr = MemoryManager()
        mgr.remember_message(Message(role=MessageRole.USER, content="test"))
        rec = TaskRecord(task_type="gen", description="test task")
        rec.mark_success()
        mgr.remember_task(rec)

        s = mgr.full_summary()
        assert "working_memory" in s
        assert "episodic_memory" in s
        assert "semantic_memory" in s
        assert "graph" in s
