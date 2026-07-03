"""ChatDev plan-graph extractor.

Turns a ChatDev trajectory (a long log string) into a runnable plan-graph
(``networkx.DiGraph``) plus a role-interaction graph, and bundles per-trace
structural metrics. Pure parsing + graph analysis: nothing is executed and no
LLM/API is called.

SCOPE GUARD: extraction + analysis only. There is deliberately no executor,
no LangGraph, and no LLM here — running a plan under different topologies is the
next, separately-gated step.
"""
from __future__ import annotations

import re
from typing import Dict, Iterator, List, Optional, Tuple

import networkx as nx

from .stats import compute_metrics

# Roles ChatDev assigns to its agents (for reference / validation).
KNOWN_ROLES = {
    "Chief Executive Officer",
    "Chief Product Officer",
    "Chief Technology Officer",
    "Programmer",
    "Code Reviewer",
    "Software Test Engineer",
    "Counselor",
}

WRITE_MARKER = "Update Codes"     # a code write -> kind="write"
RUN_MARKER = "Execute Detail"     # a code run   -> kind="run"

# A single scan recognises, in textual order, the three things we care about:
#   - an assistant direction line: **assistant_role_name** | <role> |
#   - a user direction line:       **user_role_name** | <role> |
#   - a process marker:            **[<name>]**
_TOKEN_RE = re.compile(
    r"\*\*assistant_role_name\*\*\s*\|\s*(?P<assistant>[^|]+?)\s*\|"
    r"|\*\*user_role_name\*\*\s*\|\s*(?P<user>[^|]+?)\s*\|"
    r"|\*\*\[(?P<marker>[^\]]+?)\]\*\*"
)


# --- parsing -------------------------------------------------------------
def _parse_nodes(trajectory: str) -> List[dict]:
    """Walk the trajectory left-to-right into an ordered list of plan nodes.

    One ``exchange`` node per (assistant + user) direction-line pair; one
    ``write`` per "Update Codes" marker; one ``run`` per "Execute Detail".
    Other process markers (RolePlaying, chatting, ...) are structural only and
    create no node.
    """
    nodes: List[dict] = []
    pending: Dict[str, str] = {}

    for match in _TOKEN_RE.finditer(trajectory):
        if match.group("assistant") is not None:
            pending["assistant"] = match.group("assistant").strip()
        elif match.group("user") is not None:
            pending["user"] = match.group("user").strip()
        elif match.group("marker") is not None:
            marker = match.group("marker").strip()
            if marker == WRITE_MARKER:
                nodes.append({"kind": "write"})
            elif marker == RUN_MARKER:
                nodes.append({"kind": "run"})
            # any other marker is ignored (no node)

        if "assistant" in pending and "user" in pending:
            nodes.append({
                "kind": "exchange",
                "user_role": pending["user"],
                "assistant_role": pending["assistant"],
            })
            pending = {}

    return nodes


def _add_edge(graph: nx.DiGraph, u: int, v: int, etype: str) -> None:
    """Add a typed edge, merging types if the (u, v) edge already exists.

    A DiGraph holds one edge per ordered pair, but a write->run edge can
    coincide with a spine edge when the run immediately follows the write
    (the common ChatDev case). We keep both types as ``"sequence+state"`` so no
    relationship is lost.
    """
    if graph.has_edge(u, v):
        parts = graph[u][v]["type"].split("+")
        if etype not in parts:
            parts.append(etype)
            graph[u][v]["type"] = "+".join(parts)
    else:
        graph.add_edge(u, v, type=etype)


def _build_role_graph(parsed: List[dict]) -> nx.DiGraph:
    """Role-interaction DiGraph: edge user_role -> assistant_role, weighted."""
    role_graph = nx.DiGraph()
    for node in parsed:
        if node["kind"] != "exchange":
            continue
        user_role = node["user_role"]
        assistant_role = node["assistant_role"]
        role_graph.add_node(user_role)
        role_graph.add_node(assistant_role)
        if role_graph.has_edge(user_role, assistant_role):
            role_graph[user_role][assistant_role]["weight"] += 1
        else:
            role_graph.add_edge(user_role, assistant_role, weight=1)
    return role_graph


def build_graph(trajectory: str) -> Tuple[nx.DiGraph, nx.DiGraph]:
    """Parse a trajectory into (plan-graph DAG, role-interaction graph)."""
    parsed = _parse_nodes(trajectory)

    graph = nx.DiGraph()
    for idx, node in enumerate(parsed):
        attrs = {"idx": idx, "kind": node["kind"]}
        if node["kind"] == "exchange":
            attrs["user_role"] = node["user_role"]
            attrs["assistant_role"] = node["assistant_role"]
        graph.add_node(idx, **attrs)

    # Spine: consecutive nodes i -> i+1.
    for i in range(len(parsed) - 1):
        _add_edge(graph, i, i + 1, "sequence")

    # State: each write -> the next run, and -> every exchange that follows it
    # until the next write (the nodes depending on the latest code state).
    write_idxs = [i for i, n in enumerate(parsed) if n["kind"] == "write"]
    run_idxs = [i for i, n in enumerate(parsed) if n["kind"] == "run"]
    exchange_idxs = [i for i, n in enumerate(parsed) if n["kind"] == "exchange"]

    for pos, w in enumerate(write_idxs):
        next_write = write_idxs[pos + 1] if pos + 1 < len(write_idxs) else len(parsed)
        runs_in_window = [r for r in run_idxs if w < r < next_write]
        if runs_in_window:
            _add_edge(graph, w, runs_in_window[0], "state")
        for e in exchange_idxs:
            if w < e < next_write:
                _add_edge(graph, w, e, "state")

    role_graph = _build_role_graph(parsed)
    return graph, role_graph


# --- record-level API ----------------------------------------------------
def extract_record(record) -> dict:
    """Extract the runnable serialization + metrics for one trace record."""
    graph, role_graph = build_graph(record.trajectory)
    return {
        "trace_id": record.trace_id,
        "mas_name": record.mas_name,
        "benchmark_name": record.benchmark_name,
        "metrics": compute_metrics(graph, role_graph),
        "mast_flags": dict(record.mast_flags),
        "graph_nodelink": nx.node_link_data(graph, edges="edges"),
        "role_nodelink": nx.node_link_data(role_graph, edges="edges"),
    }


def _matches(value, allowed) -> bool:
    if allowed is None:
        return True
    if isinstance(allowed, str):
        return value == allowed
    return value in set(allowed)


def iter_chatdev(loader, benchmarks=None) -> Iterator[dict]:
    """Yield ``extract_record`` for every ChatDev trace in the full dataset.

    ``loader`` is the ``mast_analysis.loader`` module (or anything exposing
    ``ensure_raw`` and ``load_full``). ``benchmarks`` optionally filters the
    benchmark (e.g. ``"ProgramDev"``).
    """
    full_path, _human_path = loader.ensure_raw()
    for record in loader.load_full(full_path):
        if record.mas_name != "ChatDev":
            continue
        if not _matches(record.benchmark_name, benchmarks):
            continue
        yield extract_record(record)


def _excerpt_around(trajectory: str, marker: str, span: int = 1500) -> str:
    """~``span``-char excerpt around the first ``**[marker]**`` occurrence."""
    needle = f"**[{marker}]**"
    pos = trajectory.find(needle)
    if pos == -1:
        return trajectory[:span]
    start = max(0, pos - 200)
    return trajectory[start:start + span]


def exemplars(
    loader,
    category: str = "2.",
    benchmarks=None,
    excerpt_chars: int = 1500,
) -> Iterator[dict]:
    """Yield ChatDev traces with any MAST flag in ``category`` (e.g. "2.").

    Each yielded dict carries the metrics, the flags, and a ~1500-char
    trajectory excerpt around the first "Execute Detail" block — the
    demonstration input for the (separately-gated) execution step.
    """
    full_path, _human_path = loader.ensure_raw()
    for record in loader.load_full(full_path):
        if record.mas_name != "ChatDev":
            continue
        if not _matches(record.benchmark_name, benchmarks):
            continue
        flags = record.mast_flags
        if not any(value and mode.startswith(category) for mode, value in flags.items()):
            continue
        graph, role_graph = build_graph(record.trajectory)
        yield {
            "trace_id": record.trace_id,
            "mas_name": record.mas_name,
            "benchmark_name": record.benchmark_name,
            "category": category,
            "metrics": compute_metrics(graph, role_graph),
            "mast_flags": dict(flags),
            "excerpt": _excerpt_around(record.trajectory, RUN_MARKER, excerpt_chars),
        }
