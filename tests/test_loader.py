"""Tests for the MAD loader — all run against the fixture, no network."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from agent_guarantees.mad.loader import MAST_MODES, load_all, load_full, load_human

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_mad.json"


@pytest.fixture
def fixture_files(tmp_path):
    """Split the single synthetic fixture into the two real file shapes."""
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    full_file = tmp_path / "full.json"
    human_file = tmp_path / "human.json"
    full_file.write_text(json.dumps(data["full"]), encoding="utf-8")
    human_file.write_text(json.dumps(data["human"]), encoding="utf-8")
    return full_file, human_file


def test_full_record_normalizes(fixture_files):
    full_file, _ = fixture_files
    recs = list(load_full(full_file))

    assert len(recs) == 1
    r = recs[0]
    assert r.source == "full"
    # trajectory is the extracted string from trace["trajectory"].
    assert isinstance(r.trajectory, str)
    assert "**[Start Chat]**" in r.trajectory
    # all 14 modes present and strictly 0/1.
    assert set(r.mast_flags.keys()) == set(MAST_MODES)
    assert all(v in (0, 1) for v in r.mast_flags.values())
    assert r.mast_flags["1.2"] == 1
    assert r.mast_flags["2.3"] == 1
    assert r.mast_flags["3.3"] == 1
    assert r.mast_flags["1.1"] == 0
    # full-only / human-only fields.
    assert r.llm_name == "gpt-4o-mini"
    assert r.round is None
    assert r.annotator_votes is None


def test_human_record_normalizes_with_majority_vote(fixture_files):
    _, human_file = fixture_files
    recs = list(load_human(human_file))

    assert len(recs) == 1
    r = recs[0]
    assert r.source == "human"
    # trajectory is the raw trace string used directly.
    assert isinstance(r.trajectory, str)
    assert "**[Coding]**" in r.trajectory
    # all 14 modes present and 0/1.
    assert set(r.mast_flags.keys()) == set(MAST_MODES)
    assert all(v in (0, 1) for v in r.mast_flags.values())
    # majority vote of the three annotators:
    assert r.mast_flags["1.1"] == 1   # T,T,F -> 2/3
    assert r.mast_flags["1.2"] == 0   # F,F,T -> 1/3
    assert r.mast_flags["2.3"] == 1   # T,F,T -> 2/3
    assert r.mast_flags["3.3"] == 0   # F,F,F -> 0/3
    # human-only / full-only fields.
    assert r.round == 1
    assert r.llm_name is None
    # raw annotator booleans are preserved for every row, mapped or not.
    assert r.annotator_votes is not None
    assert r.annotator_votes["1.1 Disobey task specification"] == {
        "annotator_1": True, "annotator_2": True, "annotator_3": False,
    }
    assert any("Other" in fm for fm in r.annotator_votes)


def test_human_unmappable_row_is_logged(fixture_files, caplog):
    _, human_file = fixture_files
    with caplog.at_level(logging.WARNING, logger="agent_guarantees.mad.loader"):
        list(load_human(human_file))
    assert "does not map to a MAST mode token" in caplog.text


def test_load_all_filtering(fixture_files):
    full_file, human_file = fixture_files

    # Matching filter: one full + one human record.
    matched = list(load_all(
        systems="ChatDev", benchmarks="ProgramDev",
        full_path=full_file, human_path=human_file,
    ))
    assert len(matched) == 2
    assert {r.source for r in matched} == {"full", "human"}

    # Non-matching system filter: nothing.
    none = list(load_all(
        systems="NoSuchSystem",
        full_path=full_file, human_path=human_file,
    ))
    assert none == []

    # Non-matching benchmark filter: nothing.
    none_bench = list(load_all(
        benchmarks="HumanEval",
        full_path=full_file, human_path=human_file,
    ))
    assert none_bench == []

    # No filter: everything.
    everything = list(load_all(full_path=full_file, human_path=human_file))
    assert len(everything) == 2


def test_load_all_accepts_iterable_filters(fixture_files):
    full_file, human_file = fixture_files
    matched = list(load_all(
        systems=["ChatDev", "MetaGPT"],
        benchmarks=["ProgramDev", "HumanEval"],
        full_path=full_file, human_path=human_file,
    ))
    assert len(matched) == 2
