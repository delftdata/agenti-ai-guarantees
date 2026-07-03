"""Task 2 execution-topology rig — a deterministic experimental apparatus.

This is pure Python + networkx: no LLM, no API, no network, no real threads. Its
job is to validate the rig and its failure-detection *before* any real agents are
involved, by reproducing two coordination failures deterministically:

  - a write-race (free-for-all read-modify-write loses updates), and
  - a stale-read (over-parallel execution reads before producers have written).

Concurrency is modelled as an explicit two-phase schedule (all reads from the
round's start-state, then all writes) so the outcomes are reproducible rather
than timing-dependent.

SCOPE GUARD: deterministic rig only. No LLM calls, no real agents, no LangGraph.
Plugging real agents into the Task callbacks and choosing the real workload is
the next, Asterios-gated step.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Tuple

import networkx as nx

from ..mad.stats import parallelizable_width as _dilworth_width

TOPOLOGIES: Tuple[str, ...] = ("sequential", "parallel", "over_parallel")
DISCIPLINES: Tuple[str, ...] = ("disciplined", "ffa")


@dataclass
class Task:
    """A plan node: an id, its parent ids (deps), and a pure step callback.

    ``step(state)`` reads from and writes to a shared dict-like State. It must be
    pure in the sense of deriving its writes only from what it reads.
    """

    id: str
    parents: List[str]
    step: Callable[[Any], None]


# --- the fan-out plan ----------------------------------------------------
def _source_step(state: Any) -> None:
    # Initialise the shared accumulator used by the ffa discipline.
    state["total"] = 0


def _make_worker_step(worker_id: str) -> Callable[[Any], None]:
    def step(state: Any) -> None:
        if state.discipline == "ffa":
            # Unsynchronised read-modify-write on one shared key.
            state["total"] = state.get("total", 0) + 1
        else:
            # Disciplined: write an own namespaced key (no shared mutation).
            state[f"contrib::{worker_id}"] = 1
    return step


def _make_sink_step(worker_ids: List[str]) -> Callable[[Any], None]:
    def step(state: Any) -> None:
        if state.discipline == "ffa":
            state["result"] = state.get("total", 0)
        else:
            # Reducer: sum the per-worker keys.
            state["result"] = sum(int(state.get(f"contrib::{w}", 0)) for w in worker_ids)
    return step


def make_fanout_plan(width: int) -> nx.DiGraph:
    """source -> ``width`` independent workers -> sink.

    Each worker contributes +1 to a shared accumulator; the sink reads it. The
    workers are mutually independent, so ``parallelizable_width == width``. The
    reference (correct) result equals ``width`` and is stored on the graph.
    """
    plan = nx.DiGraph()
    worker_ids = [f"worker_{i}" for i in range(width)]

    plan.add_node("source", task=Task("source", [], _source_step))
    for wid in worker_ids:
        plan.add_node(wid, task=Task(wid, ["source"], _make_worker_step(wid)))
        plan.add_edge("source", wid)
    plan.add_node("sink", task=Task("sink", list(worker_ids), _make_sink_step(worker_ids)))
    for wid in worker_ids:
        plan.add_edge(wid, "sink")

    plan.graph["reference"] = width
    return plan


def parallelizable_width(plan: nx.DiGraph) -> int:
    """Dilworth antichain width of the plan's dependency DAG.

    Delegates to the exact routine ``stats.compute_metrics`` uses, so the rig's
    notion of width is identical to the one applied to extracted ChatDev logs.
    """
    return _dilworth_width(plan)


# --- deterministic two-phase execution -----------------------------------
class _PhaseState:
    """Per-task view for one round: reads see the round's start snapshot only.

    Writes are buffered (not visible to sibling tasks in the same round) and
    committed after every task in the round has run. This makes "concurrency"
    an explicit all-reads-then-all-writes schedule with no real races.
    """

    def __init__(self, snapshot: Dict[str, Any], discipline: str):
        self._snapshot = snapshot
        self.writes: Dict[str, Any] = {}
        self.discipline = discipline

    def __getitem__(self, key):
        if key in self.writes:
            return self.writes[key]
        return self._snapshot[key]

    def get(self, key, default=None):
        if key in self.writes:
            return self.writes[key]
        return self._snapshot.get(key, default)

    def __setitem__(self, key, value):
        self.writes[key] = value

    def __contains__(self, key):
        return key in self.writes or key in self._snapshot


def _schedule(plan: nx.DiGraph, topology: str) -> List[List[str]]:
    """Rounds of task ids. Cost proxy is the number of rounds."""
    if topology == "sequential":
        return [[tid] for tid in nx.lexicographical_topological_sort(plan)]
    if topology == "parallel":
        return [sorted(gen) for gen in nx.topological_generations(plan)]
    if topology == "over_parallel":
        return [list(plan.nodes())]
    raise ValueError(f"unknown topology: {topology!r}")


def _run_cell(plan: nx.DiGraph, topology: str, discipline: str) -> dict:
    rounds = _schedule(plan, topology)
    committed: Dict[str, Any] = {}
    committed_ids: set = set()
    stale_read = False

    for rnd in rounds:
        snapshot = dict(committed)            # frozen start-of-round state
        buffers: List[Dict[str, Any]] = []
        for tid in rnd:
            task = plan.nodes[tid]["task"]
            # A read is stale if a parent's write has not been committed yet.
            if any(parent not in committed_ids for parent in task.parents):
                stale_read = True
            view = _PhaseState(snapshot, discipline)
            task.step(view)
            buffers.append(view.writes)
        for buf in buffers:                   # write phase
            committed.update(buf)
        committed_ids.update(rnd)

    reference = plan.graph["reference"]
    value = committed.get("result")
    lost_updates = reference - value if value is not None else reference
    return {
        "topology": topology,
        "discipline": discipline,
        "correct": value == reference,
        "value": value,
        "lost_updates": lost_updates,
        "stale_read": stale_read,
        "cost": len(rounds),
    }


def run_experiment(plan: nx.DiGraph) -> Dict[Tuple[str, str], dict]:
    """Run the full {topology} x {discipline} grid; return one dict per cell."""
    return {
        (topology, discipline): _run_cell(plan, topology, discipline)
        for topology in TOPOLOGIES
        for discipline in DISCIPLINES
    }
