"""Offline, deterministic tests for the execution-topology rig."""
from __future__ import annotations

from agent_guarantees.execlab.rig import (
    make_fanout_plan,
    parallelizable_width,
    run_experiment,
)

WIDTH = 5


def test_parallelizable_width_equals_fanout_width():
    assert parallelizable_width(make_fanout_plan(WIDTH)) == WIDTH


def test_sequential_always_correct():
    results = run_experiment(make_fanout_plan(WIDTH))
    for discipline in ("disciplined", "ffa"):
        cell = results[("sequential", discipline)]
        assert cell["correct"]
        assert cell["value"] == WIDTH
        assert cell["lost_updates"] == 0
        assert cell["cost"] == WIDTH + 2  # source + workers + sink, one per round


def test_parallel_disciplined_correct_but_ffa_loses_updates():
    results = run_experiment(make_fanout_plan(WIDTH))

    disciplined = results[("parallel", "disciplined")]
    assert disciplined["correct"]
    assert disciplined["value"] == WIDTH
    assert disciplined["cost"] == 3  # critical-path depth: source -> worker -> sink

    ffa = results[("parallel", "ffa")]
    assert not ffa["correct"]
    assert ffa["lost_updates"] > 0
    # The write-race is NOT a stale read — that distinction is the whole point.
    assert ffa["stale_read"] is False


def test_over_parallel_triggers_stale_read_for_both_disciplines():
    results = run_experiment(make_fanout_plan(WIDTH))
    for discipline in ("disciplined", "ffa"):
        cell = results[("over_parallel", discipline)]
        assert cell["stale_read"] is True
        assert not cell["correct"]
        assert cell["cost"] == 1  # everything fired in a single round


def test_grid_shape_and_determinism():
    plan = make_fanout_plan(WIDTH)
    first = run_experiment(plan)
    second = run_experiment(plan)
    assert set(first) == {
        (t, d)
        for t in ("sequential", "parallel", "over_parallel")
        for d in ("disciplined", "ffa")
    }
    # Re-running the same plan yields identical results (no real races).
    assert first == second
