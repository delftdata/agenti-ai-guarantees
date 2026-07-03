"""Explore ChatDev / ProgramDev traces from the MAD dataset.

Downloads the raw files on first run (into data/raw/), then filters to
mas_name == "ChatDev" and benchmark_name == "ProgramDev" and inspects the
first 5 records: phase markers, role counts and role-pair directions.

Run from the repo root:
    python scripts/01_explore.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make ``src/`` importable without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent_guarantees.mad.inspect_traces import inspect_record  # noqa: E402
from agent_guarantees.mad.loader import ensure_raw, load_all  # noqa: E402

SYSTEM = "ChatDev"
BENCHMARK = "ProgramDev"
N = 5


def main() -> None:
    full_path, human_path = ensure_raw()
    records = load_all(
        systems=SYSTEM,
        benchmarks=BENCHMARK,
        full_path=full_path,
        human_path=human_path,
    )

    count = 0
    for rec in records:
        inspect_record(rec)
        count += 1
        if count >= N:
            break

    if count == 0:
        print(f"No records matched mas_name={SYSTEM!r} benchmark_name={BENCHMARK!r}.")
    else:
        print(f"\nInspected {count} record(s).")


if __name__ == "__main__":
    main()
