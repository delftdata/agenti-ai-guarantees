"""Extract ChatDev plan-graphs over ChatDev/ProgramDev and report structure.

Runs ``iter_chatdev`` over the full dataset (filtered to ProgramDev), prints a
per-trace table of structural metrics, and aggregates mean/median.

Expectation under test: ChatDev plans are near-sequential, so
``parallelizable_width`` should be small. The spine links every consecutive
node, so the dependency DAG is one chain and the width is exactly 1 — this
script reports what it actually is rather than assuming it.

The only network access is the cached download inside the loader.

Run from the repo root:
    python scripts/03_extract_chatdev.py
"""
from __future__ import annotations

import statistics
import sys
from pathlib import Path
from typing import List, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mast_analysis import loader  # noqa: E402
from mast_analysis.graph import iter_chatdev  # noqa: E402

BENCHMARK = "ProgramDev"
METRIC_KEYS = ["node_count", "depth", "max_fan_out", "parallelizable_width"]


def _render_table(headers: Sequence[str], rows: Sequence[Sequence]) -> str:
    cells = [[str(c) for c in row] for row in rows]
    widths = [
        max([len(str(headers[i]))] + [len(row[i]) for row in cells])
        for i in range(len(headers))
    ]

    def line(values: Sequence[str]) -> str:
        return "| " + " | ".join(str(v).ljust(widths[i]) for i, v in enumerate(values)) + " |"

    out = [line(headers), "| " + " | ".join("-" * widths[i] for i in range(len(headers))) + " |"]
    out.extend(line(row) for row in cells)
    return "\n".join(out)


def main() -> None:
    records = list(iter_chatdev(loader, benchmarks=BENCHMARK))

    rows: List[list] = []
    collected = {k: [] for k in METRIC_KEYS}
    for rec in records:
        m = rec["metrics"]
        flagged = [mode for mode, v in rec["mast_flags"].items() if v]
        for k in METRIC_KEYS:
            collected[k].append(m[k])
        rows.append([
            rec["trace_id"],
            m["node_count"],
            m["depth"],
            m["max_fan_out"],
            m["parallelizable_width"],
            len(flagged),
            ",".join(flagged) if flagged else "-",
        ])

    headers = [
        "Trace id", "Node count", "Depth", "Max fan out",
        "Parallelizable width", "N failures", "Flags",
    ]
    print(_render_table(headers, rows))

    print(f"\nChatDev/{BENCHMARK} traces: {len(records)}")
    if not records:
        print("No matching traces.")
        return

    agg_rows = []
    for k in METRIC_KEYS:
        values = collected[k]
        agg_rows.append([
            k,
            f"{statistics.mean(values):.2f}",
            f"{statistics.median(values):.1f}",
            min(values),
            max(values),
        ])
    print()
    print(_render_table(["Metric", "Mean", "Median", "Min", "Max"], agg_rows))

    widths = collected["parallelizable_width"]
    print(
        f"\nParallelizable width: min={min(widths)} max={max(widths)} "
        f"mean={statistics.mean(widths):.2f} — "
        + ("confirms near-sequential plans (width collapses to 1 under the "
           "spine model)." if max(widths) <= 1 else
           "some traces expose parallelism wider than 1.")
    )


if __name__ == "__main__":
    main()
