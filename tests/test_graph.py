"""Offline tests for the ChatDev plan-graph extractor (no network/download)."""
from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import pytest

from agent_guarantees.mad.graph import build_graph, extract_record
from agent_guarantees.mad.stats import compute_metrics

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_mad.json"


@pytest.fixture
def sample():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["graph_sample"]


@pytest.fixture
def sample_trajectory(sample):
    return sample["trace"]["trajectory"]


def test_node_kinds_and_counts(sample_trajectory):
    graph, role_graph = build_graph(sample_trajectory)
    metrics = compute_metrics(graph, role_graph)

    # 2 exchanges + 1 write + 1 run = 4 nodes.
    assert metrics["node_count"] == 4
    assert metrics["exchange_count"] == 2
    assert metrics["write_count"] == 1
    assert metrics["run_count"] == 1


def test_spine_and_state_edges(sample_trajectory):
    graph, _ = build_graph(sample_trajectory)
    n = graph.number_of_nodes()

    # The spine links every consecutive node with a sequence edge.
    for i in range(n - 1):
        assert graph.has_edge(i, i + 1)
        assert "sequence" in graph[i][i + 1]["type"]

    # The write -> next-run state edge exists.
    write_idx = next(i for i, d in graph.nodes(data=True) if d["kind"] == "write")
    run_idx = next(i for i, d in graph.nodes(data=True) if d["kind"] == "run")
    assert graph.has_edge(write_idx, run_idx)
    assert "state" in graph[write_idx][run_idx]["type"]


def test_depth_and_width_are_small(sample_trajectory):
    graph, role_graph = build_graph(sample_trajectory)
    metrics = compute_metrics(graph, role_graph)

    # One chain of 4 nodes -> depth = 3 edges.
    assert metrics["depth"] == 3
    # The spine totally orders the nodes -> antichain width is 1 (near-sequential).
    assert metrics["parallelizable_width"] == 1
    # CEO->CTO and CTO->Programmer: each role prompts one callee.
    assert metrics["max_fan_out"] == 1


def test_role_graph_edges(sample_trajectory):
    _, role_graph = build_graph(sample_trajectory)
    assert role_graph.has_edge("Chief Executive Officer", "Chief Technology Officer")
    assert role_graph.has_edge("Chief Technology Officer", "Programmer")
    assert role_graph["Chief Executive Officer"]["Chief Technology Officer"]["weight"] == 1


def test_extract_record_serialization_roundtrips(sample, tmp_path):
    # Load the sample as a real TraceRecord via the loader (still offline).
    from agent_guarantees.mad.loader import load_full

    full_file = tmp_path / "g.json"
    full_file.write_text(json.dumps([sample]), encoding="utf-8")
    record = next(iter(load_full(full_file)))

    out = extract_record(record)
    assert out["trace_id"] == "graph-0001"
    assert out["mas_name"] == "ChatDev"
    assert out["metrics"]["node_count"] == 4
    assert set(out["mast_flags"]) >= {"2.2"}

    # The node_link serialization is runnable: it round-trips back to a DiGraph.
    restored = nx.node_link_graph(out["graph_nodelink"], edges="edges")
    assert restored.number_of_nodes() == 4
    assert restored.is_directed()
    role_restored = nx.node_link_graph(out["role_nodelink"], edges="edges")
    assert role_restored.number_of_nodes() == 3
