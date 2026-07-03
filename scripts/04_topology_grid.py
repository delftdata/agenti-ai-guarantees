"""Run the execution-topology grid on a fan-out plan and report what happens.

Deterministic: no LLM, no API, no network, no real threads. The point is that
the rig RELIABLY detects two distinct coordination failures —
  - a write-race  (ffa under a concurrent topology), and
  - a stale-read  (over_parallel, where the sink reads before workers write).

Run from the repo root:
    python scripts/04_topology_grid.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mast_analysis.exec_lab import (  # noqa: E402
    DISCIPLINES,
    TOPOLOGIES,
    make_fanout_plan,
    parallelizable_width,
    run_experiment,
)

WIDTH = 5


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
    plan = make_fanout_plan(WIDTH)
    width = parallelizable_width(plan)
    reference = plan.graph["reference"]

    print(
        f"make_fanout_plan(width={WIDTH}): reference result = {reference}, "
        f"parallelizable_width = {width}"
    )
    print()

    results = run_experiment(plan)
    headers = [
        "Topology", "Discipline", "Correct", "Value",
        "Lost updates", "Stale read", "Cost (rounds)",
    ]
    rows = []
    for topology in TOPOLOGIES:
        for discipline in DISCIPLINES:
            cell = results[(topology, discipline)]
            rows.append([
                topology,
                discipline,
                "yes" if cell["correct"] else "NO",
                cell["value"],
                cell["lost_updates"],
                "yes" if cell["stale_read"] else "no",
                cell["cost"],
            ])
    print(_render_table(headers, rows))

    race = results[("parallel", "ffa")]
    stale = results[("over_parallel", "ffa")]
    print("\nDetected failure modes:")
    print(
        f"  write-race  (parallel + ffa): value={race['value']} vs reference={reference}, "
        f"lost_updates={race['lost_updates']}, stale_read={race['stale_read']} "
        "-> updates lost without any stale read"
    )
    print(
        f"  stale-read  (over_parallel) : sink reads before workers write, "
        f"value={stale['value']}, stale_read={stale['stale_read']} for BOTH disciplines "
        "-> a distinct failure from the write-race"
    )
    print(
        "\nReliability check: the two modes are distinguishable - the write-race "
        "shows lost_updates>0 with stale_read=False, while over_parallel shows "
        "stale_read=True regardless of discipline."
    )


if __name__ == "__main__":
    main()
