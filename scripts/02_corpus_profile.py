"""Reproducible whole-corpus profile of the MAD dataset.

Regenerates every number cited in docs/findings.md and writes the tables to
docs/corpus_profile.md. The only network access is the cached
``hf_hub_download`` inside the loader (``ensure_raw``); all computation below is
deterministic and contains no timestamps, so re-running yields byte-identical
output.

Run from the repo root:
    python scripts/02_corpus_profile.py
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

# Make ``src/`` importable without installing the package.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mast_analysis.loader import (  # noqa: E402
    MAST_MODES,
    ensure_raw,
    load_full,
    load_human,
)

DOCS = ROOT / "docs"
OUT_FILE = DOCS / "corpus_profile.md"

# The 14 modes split into the three MAST categories by their leading digit.
SPEC = [m for m in MAST_MODES if m.startswith("1.")]    # specification
COORD = [m for m in MAST_MODES if m.startswith("2.")]   # coordination
VERIF = [m for m in MAST_MODES if m.startswith("3.")]   # verification

CATEGORIES = [
    ("Specification (1.x)", SPEC),
    ("Coordination (2.x)", COORD),
    ("Verification (3.x)", VERIF),
]


# --- small helpers -------------------------------------------------------
def _pct(num: float, den: float) -> str:
    """Format a ratio as a one-decimal percentage; ``0.0%`` when den == 0."""
    return f"{(100.0 * num / den) if den else 0.0:.1f}%"


def _flagged(record) -> bool:
    return any(record.mast_flags.get(m, 0) for m in MAST_MODES)


def _any_in(record, modes: Sequence[str]) -> bool:
    return any(record.mast_flags.get(m, 0) for m in modes)


def _group_stats(group: Sequence) -> Tuple[int, int, int, int, int]:
    """Return (n, fail, spec, coord, verif) counts for a list of records."""
    n = len(group)
    fail = sum(1 for r in group if _flagged(r))
    spec = sum(1 for r in group if _any_in(r, SPEC))
    coord = sum(1 for r in group if _any_in(r, COORD))
    verif = sum(1 for r in group if _any_in(r, VERIF))
    return n, fail, spec, coord, verif


def render_table(headers: Sequence, rows: Sequence[Sequence]) -> str:
    """Render an aligned GitHub-flavoured markdown table."""
    headers = [str(h) for h in headers]
    cells = [[str(c) for c in row] for row in rows]
    widths = [
        max([len(headers[i])] + [len(row[i]) for row in cells])
        for i in range(len(headers))
    ]

    def line(values: Sequence[str]) -> str:
        return "| " + " | ".join(v.ljust(widths[i]) for i, v in enumerate(values)) + " |"

    out = [line(headers), "| " + " | ".join("-" * widths[i] for i in range(len(headers))) + " |"]
    out.extend(line(row) for row in cells)
    return "\n".join(out)


# --- table builders (each returns plain data; no I/O) --------------------
def overview(records: Sequence) -> List[list]:
    total = len(records)
    systems = sorted({r.mas_name for r in records})
    benchmarks = sorted({r.benchmark_name for r in records})
    llms = sorted({r.llm_name for r in records if r.llm_name})
    fail = sum(1 for r in records if _flagged(r))
    return [
        ["Total traces", total],
        ["Systems", len(systems)],
        ["Benchmarks", len(benchmarks)],
        ["LLMs present", ", ".join(llms) if llms else "(none)"],
        ["Overall failure rate", f"{_pct(fail, total)} ({fail}/{total})"],
    ]


def mode_frequency(records: Sequence) -> List[list]:
    """Per-mode count of flagged traces and share of the corpus."""
    total = len(records)
    rows = []
    for mode in MAST_MODES:
        count = sum(1 for r in records if r.mast_flags.get(mode, 0))
        rows.append([mode, count, _pct(count, total)])
    return rows


def category_shares(records: Sequence) -> List[list]:
    """Share of traces with >=1 mode flagged in each MAST category."""
    total = len(records)
    rows = []
    for label, modes in CATEGORIES:
        count = sum(1 for r in records if _any_in(r, modes))
        rows.append([label, count, _pct(count, total)])
    return rows


def _grouped(records: Sequence, key) -> Dict[str, list]:
    groups: Dict[str, list] = defaultdict(list)
    for r in records:
        groups[key(r)].append(r)
    return groups


def _breakdown_rows(groups: Dict[str, list]) -> List[list]:
    """Rows of (name, n, fail%, spec%, coord%, verif%), sorted by n desc."""
    rows = []
    for name in sorted(groups, key=lambda k: (-len(groups[k]), k)):
        n, fail, spec, coord, verif = _group_stats(groups[name])
        rows.append([
            name, n,
            _pct(fail, n), _pct(spec, n), _pct(coord, n), _pct(verif, n),
        ])
    return rows


def by_system(records: Sequence) -> List[list]:
    return _breakdown_rows(_grouped(records, lambda r: r.mas_name))


def by_benchmark(records: Sequence) -> List[list]:
    return _breakdown_rows(_grouped(records, lambda r: r.benchmark_name))


def by_llm(records: Sequence) -> List[list]:
    """Rows of (LLM, n, fail%, coord%), sorted by n desc; skips unlabelled."""
    groups = _grouped((r for r in records if r.llm_name), lambda r: r.llm_name)
    rows = []
    for name in sorted(groups, key=lambda k: (-len(groups[k]), k)):
        n, fail, _spec, coord, _verif = _group_stats(groups[name])
        rows.append([name, n, _pct(fail, n), _pct(coord, n)])
    return rows


def confound_check(records: Sequence) -> Tuple[List[list], List[str]]:
    """Per benchmark: the systems running it, flagging the multi-system ones.

    Returns (rows, shared) where ``shared`` lists benchmarks run by >1 system.
    """
    bench_systems: Dict[str, set] = defaultdict(set)
    for r in records:
        bench_systems[r.benchmark_name].add(r.mas_name)

    rows = []
    shared = []
    for bench in sorted(bench_systems):
        systems = sorted(bench_systems[bench])
        multi = len(systems) > 1
        if multi:
            shared.append(bench)
        rows.append([
            bench, len(systems), ", ".join(systems),
            "yes (confound)" if multi else "no",
        ])
    return rows, shared


def label_reliability(human_records: Sequence) -> List[list]:
    """Inter-annotator reliability over human (trace x annotation-row) judgments.

    Only rows with annotator_1/2/3 all present are counted. Reports the judgment
    count, % unanimous, and mean pairwise agreement (mean over the 3 annotator
    pairs of whether they agree, averaged across all judgments).
    """
    keys = ("annotator_1", "annotator_2", "annotator_3")
    judgments = 0
    unanimous = 0
    pairwise_sum = 0.0
    for rec in human_records:
        for row in rec.raw.get("annotations", []):
            if any(row.get(k) is None for k in keys):
                continue
            judgments += 1
            a1, a2, a3 = (bool(row[k]) for k in keys)
            if a1 == a2 == a3:
                unanimous += 1
            agree = (a1 == a2) + (a1 == a3) + (a2 == a3)
            pairwise_sum += agree / 3.0

    mean_pairwise = (pairwise_sum / judgments) if judgments else 0.0
    return [
        ["Judgments (rows with all 3 annotators)", judgments],
        ["Unanimous", f"{_pct(unanimous, judgments)} ({unanimous}/{judgments})"],
        ["Mean pairwise agreement", f"{100.0 * mean_pairwise:.1f}%"],
    ]


# --- report assembly -----------------------------------------------------
def build_report(full_records: Sequence, human_records: Sequence) -> str:
    sections: List[str] = []

    sections.append(
        "# MAD corpus profile\n\n"
        "Generated by `scripts/02_corpus_profile.py` from the cached MAD files. "
        "Deterministic (no timestamps): re-run to regenerate.\n\n"
        "- Corpus tables (1-6) are over `MAD_full_dataset.json` (the 14-mode "
        "`mast_annotation`).\n"
        "- Table 7 is over `MAD_human_labelled_dataset.json`.\n"
    )

    sections.append(
        "## 1. Overview\n\n"
        + render_table(["Metric", "Value"], overview(full_records))
    )

    cat_rows = category_shares(full_records)
    sections.append(
        "## 2. Corpus-wide mode frequency\n\n"
        + render_table(["Mode", "Traces flagged", "Share of traces"],
                       mode_frequency(full_records))
        + "\n\nCategory-level share (any mode in the category flagged):\n\n"
        + render_table(["Category", "Traces flagged", "Share of traces"], cat_rows)
    )

    breakdown_headers = ["System", "N", "Fail %", "Spec %", "Coord %", "Verif %"]
    sections.append(
        "## 3. By system\n\n"
        + render_table(breakdown_headers, by_system(full_records))
    )

    sections.append(
        "## 4. By benchmark\n\n"
        + render_table(["Benchmark", "N", "Fail %", "Spec %", "Coord %", "Verif %"],
                       by_benchmark(full_records))
    )

    conf_rows, shared = confound_check(full_records)
    shared_note = (
        "Benchmarks run by more than one system (system is confounded with "
        "benchmark here): **" + ", ".join(shared) + "**."
        if shared else
        "No benchmark is run by more than one system - system and benchmark do "
        "not overlap in this corpus."
    )
    sections.append(
        "## 5. Confound check\n\n"
        + render_table(["Benchmark", "System count", "Systems", "Run by >1 system"],
                       conf_rows)
        + "\n\n" + shared_note
    )

    sections.append(
        "## 6. By LLM\n\n"
        + render_table(["LLM", "N", "Fail %", "Coord %"], by_llm(full_records))
    )

    sections.append(
        "## 7. Label reliability (human-labelled file)\n\n"
        + render_table(["Metric", "Value"], label_reliability(human_records))
    )

    return "\n\n".join(sections) + "\n"


def main() -> None:
    full_path, human_path = ensure_raw()
    full_records = list(load_full(full_path))
    human_records = list(load_human(human_path))

    report = build_report(full_records, human_records)
    print(report)

    DOCS.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(report, encoding="utf-8")
    print(f"\nWrote {OUT_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
