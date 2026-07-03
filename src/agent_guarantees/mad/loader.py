"""Loader for the MAD multi-agent failure dataset.

Downloads the two MAD JSON files from the Hugging Face Hub and normalizes
both (rather different) file shapes into a single :class:`TraceRecord` form.

Network is touched *only* by :func:`download_raw` / :func:`ensure_raw`.
``load_full`` / ``load_human`` / ``load_all`` read already-downloaded JSON
files and never reach the network — that is what the test-suite relies on.
"""
from __future__ import annotations

import itertools
import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# --- dataset coordinates -------------------------------------------------
REPO_ID = "mcemri/MAD"
REPO_TYPE = "dataset"
FULL_FILENAME = "MAD_full_dataset.json"        # JSON array, 1242 records
HUMAN_FILENAME = "MAD_human_labelled_dataset.json"  # JSON array, 19 records

# The 14 MAST failure-mode keys, exactly as stored in the ``mast_annotation``
# dict of the full dataset: 5 + 6 + 3 = 14.
MAST_MODES: List[str] = [
    "1.1", "1.2", "1.3", "1.4", "1.5",
    "2.1", "2.2", "2.3", "2.4", "2.5", "2.6",
    "3.1", "3.2", "3.3",
]

# Default raw-data location: <cwd>/data/raw, overridable via the MAD_DATA_DIR
# environment variable. Every loader function also accepts an explicit path.
DATA_RAW = Path(os.environ.get("MAD_DATA_DIR", "") or Path.cwd() / "data" / "raw")

# Leading "X.Y" token of a human "failure mode" string, e.g. "1.2 Disobey ...".
_MODE_TOKEN_RE = re.compile(r"^\s*(\d+\.\d+)\b")


@dataclass
class TraceRecord:
    """A single trace, normalized across the two MAD file shapes."""

    mas_name: str
    benchmark_name: str
    trace_id: str
    source: str                          # "full" | "human"
    trajectory: str                      # the log string
    mast_flags: Dict[str, int]           # all 14 modes, values 0/1
    raw: dict                            # the original, untouched record
    llm_name: Optional[str] = None       # present on full, absent on human
    round: Optional[int] = None          # present on human, absent on full
    # Human source only: the raw per-failure-mode annotator booleans, keyed by
    # the original "failure mode" string (preserves all rows, mapped or not).
    annotator_votes: Optional[Dict[str, Dict[str, bool]]] = None


# --- network: the only functions that download anything ------------------
def download_raw(data_dir: Union[str, Path] = DATA_RAW) -> Tuple[Path, Path]:
    """Download both MAD JSON files into ``data_dir`` and return their paths."""
    from huggingface_hub import hf_hub_download  # lazy: keep import off test path

    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    full_path = hf_hub_download(
        repo_id=REPO_ID, repo_type=REPO_TYPE,
        filename=FULL_FILENAME, local_dir=str(data_dir),
    )
    human_path = hf_hub_download(
        repo_id=REPO_ID, repo_type=REPO_TYPE,
        filename=HUMAN_FILENAME, local_dir=str(data_dir),
    )
    logger.info("Downloaded MAD files into %s", data_dir)
    return Path(full_path), Path(human_path)


def ensure_raw(data_dir: Union[str, Path] = DATA_RAW) -> Tuple[Path, Path]:
    """Return paths to the two raw files, downloading them only if missing."""
    data_dir = Path(data_dir)
    full_path = data_dir / FULL_FILENAME
    human_path = data_dir / HUMAN_FILENAME
    if full_path.exists() and human_path.exists():
        return full_path, human_path
    return download_raw(data_dir)


# --- normalization -------------------------------------------------------
def _read_json(path: Union[str, Path]) -> list:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _normalize_full(rec: dict) -> TraceRecord:
    """Normalize one record from ``MAD_full_dataset.json``.

    Here ``trace`` is a dict ``{"key", "index", "trajectory"}`` and the log
    string lives at ``trace["trajectory"]``. ``mast_annotation`` is the dict of
    14 keys with 0/1 values.
    """
    trace = rec.get("trace") or {}
    trajectory = trace.get("trajectory", "") if isinstance(trace, dict) else str(trace)
    annotation = rec.get("mast_annotation") or {}
    mast_flags = {mode: int(annotation.get(mode, 0)) for mode in MAST_MODES}
    return TraceRecord(
        mas_name=rec.get("mas_name"),
        benchmark_name=rec.get("benchmark_name"),
        trace_id=rec.get("trace_id"),
        source="full",
        trajectory=trajectory,
        mast_flags=mast_flags,
        raw=rec,
        llm_name=rec.get("llm_name"),
        round=None,
    )


def _normalize_human(rec: dict) -> TraceRecord:
    """Normalize one record from ``MAD_human_labelled_dataset.json``.

    Here ``trace`` is itself the raw log string (NOT a dict), and labels live
    in ``annotations`` — a list of ``{"failure mode", "annotator_1..3"}`` rows.

    NOTE on 14 vs 18: the full file uses the 14 ``mast_annotation`` keys, while
    the human file uses 18 "failure mode" rows. We map each human row onto the
    14 modes by parsing its leading "X.Y" token; rows whose token is missing or
    not one of the 14 modes are logged and skipped. Per mode the 0/1 flag is the
    majority vote of the three annotators; on token collisions we keep the max
    so a detected failure is never silently dropped. The raw annotator booleans
    for every row (mapped or not) are preserved on ``annotator_votes``.
    """
    trace = rec.get("trace")
    trajectory = trace if isinstance(trace, str) else ""
    annotations = rec.get("annotations") or []

    mast_flags = {mode: 0 for mode in MAST_MODES}
    annotator_votes: Dict[str, Dict[str, bool]] = {}

    for row in annotations:
        fm = str(row.get("failure mode", ""))
        a1 = bool(row.get("annotator_1"))
        a2 = bool(row.get("annotator_2"))
        a3 = bool(row.get("annotator_3"))
        annotator_votes[fm] = {"annotator_1": a1, "annotator_2": a2, "annotator_3": a3}

        m = _MODE_TOKEN_RE.match(fm)
        if not m:
            logger.warning(
                "Human trace %s: failure mode %r does not map to a MAST mode token",
                rec.get("trace_id"), fm,
            )
            continue
        mode = m.group(1)
        if mode not in MAST_MODES:
            logger.warning(
                "Human trace %s: parsed mode %r (from %r) is not one of the 14 MAST modes",
                rec.get("trace_id"), mode, fm,
            )
            continue
        majority = 1 if (a1 + a2 + a3) >= 2 else 0
        mast_flags[mode] = max(mast_flags[mode], majority)

    return TraceRecord(
        mas_name=rec.get("mas_name"),
        benchmark_name=rec.get("benchmark_name"),
        trace_id=rec.get("trace_id"),
        source="human",
        trajectory=trajectory,
        mast_flags=mast_flags,
        raw=rec,
        llm_name=None,
        round=rec.get("round"),
        annotator_votes=annotator_votes,
    )


# --- public iterators ----------------------------------------------------
def load_full(path: Optional[Union[str, Path]] = None) -> Iterator[TraceRecord]:
    """Yield normalized records from the full dataset file."""
    if path is None:
        path = DATA_RAW / FULL_FILENAME
    for rec in _read_json(path):
        yield _normalize_full(rec)


def load_human(path: Optional[Union[str, Path]] = None) -> Iterator[TraceRecord]:
    """Yield normalized records from the human-labelled dataset file."""
    if path is None:
        path = DATA_RAW / HUMAN_FILENAME
    for rec in _read_json(path):
        yield _normalize_human(rec)


def _as_set(value) -> Optional[set]:
    if value is None:
        return None
    if isinstance(value, str):
        return {value}
    return set(value)


def load_all(
    systems=None,
    benchmarks=None,
    full_path: Optional[Union[str, Path]] = None,
    human_path: Optional[Union[str, Path]] = None,
) -> Iterator[TraceRecord]:
    """Yield records from both files, filtered by mas_name / benchmark_name.

    ``systems`` / ``benchmarks`` accept a single string or any iterable of
    strings; ``None`` means "no filter".
    """
    systems = _as_set(systems)
    benchmarks = _as_set(benchmarks)
    for rec in itertools.chain(load_full(full_path), load_human(human_path)):
        if systems is not None and rec.mas_name not in systems:
            continue
        if benchmarks is not None and rec.benchmark_name not in benchmarks:
            continue
        yield rec
