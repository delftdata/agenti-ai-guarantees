"""The failed-vs-clean builders run against in-test records (no real data)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "05_failed_vs_clean.py"


@pytest.fixture(scope="module")
def fvc():
    """Load scripts/05_failed_vs_clean.py by path (its name starts with a digit)."""
    spec = importlib.util.spec_from_file_location("failed_vs_clean", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _record(trace_id: str, flags: dict, **metric_overrides) -> dict:
    """A minimal extract_record-shaped dict: metrics + mast_flags."""
    from agent_guarantees.mad.loader import MAST_MODES

    metrics = {
        "node_count": 10, "exchange_count": 6, "write_count": 2,
        "run_count": 2, "depth": 9, "max_fan_out": 2,
        "parallelizable_width": 1,
    }
    metrics.update(metric_overrides)
    return {
        "trace_id": trace_id,
        "mas_name": "ChatDev",
        "benchmark_name": "ProgramDev",
        "metrics": metrics,
        "mast_flags": {mode: flags.get(mode, 0) for mode in MAST_MODES},
    }


@pytest.fixture
def records():
    """Two failed traces (one 1.x, one 2.x) and two clean ones."""
    return [
        _record("t-spec", {"1.1": 1}, exchange_count=8, node_count=12),
        _record("t-coord", {"2.6": 1}, exchange_count=4, node_count=8),
        _record("t-clean-a", {}),
        _record("t-clean-b", {}, run_count=4),
    ]


def test_split_groups_correctly(fvc, records):
    failed, clean = fvc.split_failed_clean(records)
    assert [r["trace_id"] for r in failed] == ["t-spec", "t-coord"]
    assert [r["trace_id"] for r in clean] == ["t-clean-a", "t-clean-b"]


def test_aggregate_rows_cover_both_groups(fvc, records):
    failed, clean = fvc.split_failed_clean(records)
    rows = fvc.aggregate_rows(failed, clean)

    # One row per metric: (metric, failed mean, failed median, clean mean,
    # clean median) — both group columns are populated, not "-".
    assert [row[0] for row in rows] == fvc.METRIC_KEYS
    by_metric = {row[0]: row for row in rows}
    assert by_metric["exchange_count"][1:] == ["6.00", "6.0", "6.00", "6.0"]
    assert by_metric["run_count"][3:] == ["3.00", "3.0"]  # clean: 2 and 4


def test_category_rows_pick_up_coordination_record(fvc, records):
    rows = fvc.category_rows(records)
    coord = [r for r in rows if r[0].startswith("Coordination")]
    assert len(coord) == len(fvc.METRIC_KEYS)
    # Only t-coord is 2.x-flagged, so n == 1 and its metrics come through.
    assert all(r[1] == 1 for r in coord)
    by_metric = {r[2]: r for r in coord}
    assert by_metric["exchange_count"][3:] == ["4.00", "4.0"]


def test_build_report_renders_both_sections(fvc, records):
    report = fvc.build_report(records)
    assert isinstance(report, str) and report.strip()
    for heading in (
        "## 1. Group sizes and aggregate metrics",
        "## 2. Per-MAST-category split",
    ):
        assert heading in report
    # 2/2 differs from the expected 93/37, so the drift warning fires.
    assert "WARNING" in report
