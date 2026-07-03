"""The corpus profile builders run against the fixture (no real data)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "02_corpus_profile.py"
FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_mad.json"


@pytest.fixture(scope="module")
def profile():
    """Load scripts/02_corpus_profile.py by path (its name starts with a digit)."""
    spec = importlib.util.spec_from_file_location("corpus_profile", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def records(tmp_path):
    """Split the synthetic fixture into the two real file shapes and load them."""
    from agent_guarantees.mad.loader import load_full, load_human

    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    full_file = tmp_path / "full.json"
    human_file = tmp_path / "human.json"
    full_file.write_text(json.dumps(data["full"]), encoding="utf-8")
    human_file.write_text(json.dumps(data["human"]), encoding="utf-8")
    return list(load_full(full_file)), list(load_human(human_file))


def test_table_builders_run(profile, records):
    full, human = records

    # Each builder returns non-empty data without raising.
    assert profile.overview(full)
    assert profile.mode_frequency(full)
    assert profile.category_shares(full)
    assert profile.by_system(full)
    assert profile.by_benchmark(full)
    assert profile.by_llm(full)
    assert profile.label_reliability(human)

    conf_rows, shared = profile.confound_check(full)
    assert conf_rows
    assert isinstance(shared, list)

    # mode_frequency covers all 14 modes.
    assert len(profile.mode_frequency(full)) == 14


def test_build_report_renders(profile, records):
    full, human = records
    report = profile.build_report(full, human)
    assert isinstance(report, str) and report.strip()
    # All seven sections are present.
    for heading in (
        "## 1. Overview",
        "## 2. Corpus-wide mode frequency",
        "## 3. By system",
        "## 4. By benchmark",
        "## 5. Confound check",
        "## 6. By LLM",
        "## 7. Label reliability",
    ):
        assert heading in report


def test_label_reliability_counts_fixture(profile, records):
    _full, human = records
    rows = dict((r[0], r[1]) for r in profile.label_reliability(human))
    # The fixture human record has 5 annotation rows, all with 3 annotators.
    assert rows["Judgments (rows with all 3 annotators)"] == 5
