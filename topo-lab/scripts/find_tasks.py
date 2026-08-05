"""Rank SWE-bench Lite instances as candidates for the gradient experiment.

Wanted shape: the fix is NOT spelled out in the problem statement (so an
analysis node's output is load-bearing), but the statement points at the
right area (so a fixed graph can plausibly localize it); the gold patch
touches several sites (so partial damage grades as partial failure); and
several FAIL_TO_PASS tests exist (graded resolution is not all-or-nothing).
Repos restricted to ones whose test suites run in a plain Python venv.

Usage:  python scripts/find_tasks.py [--top 15]
"""

import argparse
import json
import re

from datasets import load_dataset

EASY_REPOS = {
    "django/django", "sympy/sympy", "psf/requests", "pallets/flask",
    "sphinx-doc/sphinx", "pylint-dev/pylint", "pytest-dev/pytest",
}


def added_lines(patch: str):
    return [l[1:].strip() for l in patch.splitlines()
            if l.startswith("+") and not l.startswith("+++") and l[1:].strip()]


def patched_files(patch: str):
    return re.findall(r"^diff --git a/(\S+)", patch, re.MULTILINE)


def analyze(row):
    patch = row["patch"]
    stmt = row["problem_statement"]
    files = patched_files(patch)
    hunks = len(re.findall(r"^@@ ", patch, re.MULTILINE))
    f2p = len(json.loads(row["FAIL_TO_PASS"]))
    adds = added_lines(patch)
    # fraction of the fix's added lines quoted verbatim in the statement
    leaked = sum(1 for l in adds if len(l) > 10 and l in stmt)
    leak_frac = leaked / len(adds) if adds else 1.0
    # does the statement mention any patched file or its module name?
    mentioned = any(
        (f in stmt) or (f.rsplit("/", 1)[-1] in stmt)
        or (f.rsplit("/", 1)[-1].removesuffix(".py") in stmt)
        for f in files)
    score = (
        min(hunks, 6)                      # multi-site edits
        + 2 * min(f2p, 4)                  # graded resolution possible
        + (4 if leak_frac == 0 else 0)     # fix not in statement
        + (2 if mentioned else 0)          # localization plausible at plan time
        + (1 if len(files) > 1 else 0)
    )
    return {
        "instance_id": row["instance_id"], "repo": row["repo"],
        "files": len(files), "hunks": hunks, "f2p": f2p,
        "leak_frac": round(leak_frac, 2), "stmt_mentions_file": mentioned,
        "stmt_chars": len(stmt), "score": score,
        "patched": files[:3],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args()

    ds = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
    cands = [analyze(r) for r in ds if r["repo"] in EASY_REPOS]
    cands.sort(key=lambda c: -c["score"])

    print(f"{'instance_id':<38} {'files':>5} {'hunks':>5} {'f2p':>4} "
          f"{'leak':>5} {'named':>5} {'score':>5}  patched files")
    for c in cands[:args.top]:
        print(f"{c['instance_id']:<38} {c['files']:>5} {c['hunks']:>5} "
              f"{c['f2p']:>4} {c['leak_frac']:>5} "
              f"{str(c['stmt_mentions_file']):>5} {c['score']:>5}  "
              f"{', '.join(c['patched'])}")
    print("\nleak = fraction of the fix's added lines quoted in the problem "
          "statement (want 0). named = statement mentions a patched file "
          "(want True).")


if __name__ == "__main__":
    main()
