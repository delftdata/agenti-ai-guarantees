"""Per-graph structural metrics for ChatDev plan-graphs.

Pure graph analysis over the DAG produced by ``graph.build_graph``. No parsing,
no I/O, no LLM. The dependency DAG passed in here already contains both the
sequence (spine) edges and the state edges; every metric is computed on that.
"""
from __future__ import annotations

from typing import Dict

import networkx as nx


def _count_kind(graph: nx.DiGraph, kind: str) -> int:
    return sum(1 for _, data in graph.nodes(data=True) if data.get("kind") == kind)


def dependency_depth(graph: nx.DiGraph) -> int:
    """Longest dependency chain, in edges (``dag_longest_path_length``).

    Because the spine links every consecutive node, this is typically
    ``node_count - 1`` — i.e. the plan is one long chain.
    """
    if graph.number_of_nodes() == 0:
        return 0
    return nx.dag_longest_path_length(graph)


def max_fan_out(role_graph: nx.DiGraph) -> int:
    """Maximum out-degree in the role-interaction graph (distinct callees)."""
    if role_graph.number_of_nodes() == 0:
        return 0
    return max((deg for _, deg in role_graph.out_degree()), default=0)


def parallelizable_width(graph: nx.DiGraph) -> int:
    """Maximum antichain size of the dependency DAG.

    By Dilworth's theorem this equals the minimum path cover, which equals
    ``node_count - (maximum bipartite matching of the DAG's transitive
    closure)``. We never enumerate antichains.

    Note: the spine makes every pair of nodes comparable, so the transitive
    closure is a total order and the width collapses to 1 for any non-empty
    ChatDev plan — exactly the "near-sequential" expectation. The full Dilworth
    computation is kept so the metric stays correct for any future graph model
    whose spine is not a single chain.
    """
    n = graph.number_of_nodes()
    if n == 0:
        return 0

    closure = nx.transitive_closure_dag(graph)

    bipartite = nx.Graph()
    left = [("L", node) for node in graph.nodes]
    right = [("R", node) for node in graph.nodes]
    bipartite.add_nodes_from(left)
    bipartite.add_nodes_from(right)
    for u, v in closure.edges():
        if u != v:
            bipartite.add_edge(("L", u), ("R", v))

    if bipartite.number_of_edges() == 0:
        matching_size = 0
    else:
        left_set = set(left)
        matching = nx.bipartite.maximum_matching(bipartite, top_nodes=left_set)
        matching_size = sum(1 for key in matching if key in left_set)

    return n - matching_size


def compute_metrics(graph: nx.DiGraph, role_graph: nx.DiGraph) -> Dict[str, int]:
    """Bundle every per-trace structural metric into one dict."""
    return {
        "node_count": graph.number_of_nodes(),
        "exchange_count": _count_kind(graph, "exchange"),
        "write_count": _count_kind(graph, "write"),
        "run_count": _count_kind(graph, "run"),
        "depth": dependency_depth(graph),
        "max_fan_out": max_fan_out(role_graph),
        "parallelizable_width": parallelizable_width(graph),
    }
