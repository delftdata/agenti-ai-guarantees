"""Lightweight inspectors for MAD trace records.

This pass only understands ChatDev's log structure, which is what the
exploration script targets. It is deliberately read-only / print-only: no
graph or statistics extraction yet (those are gated on review of this pass).
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Dict, List, Tuple

# Phase markers in ChatDev logs look like: **[Coding]**, **[Testing]**, ...
PHASE_RE = re.compile(r"\*\*\[(.+?)\]\*\*")

# Role identifiers ChatDev assigns to its agents.
ROLE_RE = re.compile(
    r"Chief .*? Officer|Programmer|Code Reviewer|Software Test Engineer|Counselor"
)

# Direction lines naming the two ends of a role-play exchange.
USER_ROLE_RE = re.compile(r"user_role_name\s*[:=]\s*(.+)")
ASSISTANT_ROLE_RE = re.compile(r"assistant_role_name\s*[:=]\s*(.+)")


def _clean(value: str) -> str:
    return value.strip().strip("[]'\"").strip()


def ordered_phases(text: str) -> List[str]:
    """Distinct phase markers, in first-seen order."""
    phases: List[str] = []
    seen = set()
    for m in PHASE_RE.finditer(text):
        marker = m.group(1)
        if marker not in seen:
            seen.add(marker)
            phases.append(marker)
    return phases


def role_counts(text: str) -> Counter:
    """Counter of ChatDev role identifiers found in the log."""
    return Counter(ROLE_RE.findall(text))


def role_pairs(text: str) -> List[Tuple[str, str]]:
    """(user_role, assistant_role) direction pairs, paired in textual order."""
    users = [_clean(m.group(1)) for m in USER_ROLE_RE.finditer(text)]
    assistants = [_clean(m.group(1)) for m in ASSISTANT_ROLE_RE.finditer(text)]
    return list(zip(users, assistants))


def analyze_chatdev(text: str) -> Dict:
    """Bundle the three ChatDev-structure extractions for one trajectory."""
    return {
        "phases": ordered_phases(text),
        "roles": role_counts(text),
        "role_pairs": Counter(role_pairs(text)),
    }


def inspect_record(record) -> Dict:
    """Print a summary of one record; return the structured analysis (or {})."""
    print(
        f"=== {record.trace_id} | {record.mas_name} / {record.benchmark_name} "
        f"| source={record.source} ==="
    )
    print(f"  trajectory length: {len(record.trajectory):,} chars")

    analysis: Dict = {}
    if record.mas_name == "ChatDev":
        analysis = analyze_chatdev(record.trajectory)
        print(f"  phases ({len(analysis['phases'])}): {analysis['phases']}")
        print(f"  roles: {dict(analysis['roles'])}")
        if analysis["role_pairs"]:
            print("  role pairs (user_role_name -> assistant_role_name):")
            for (user, assistant), count in analysis["role_pairs"].most_common():
                print(f"    {user} -> {assistant}  x{count}")
        else:
            print("  role pairs: none found")
    return analysis
