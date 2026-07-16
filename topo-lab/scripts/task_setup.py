"""Pull the two selected SWE-bench Lite instances, clone their repos at the
base commit, and write a frozen task_context.md per task.

The context file is the single source of truth fed to every harness model and
every executor node. The gold patch and test patch are stored separately under
tasks/<id>/gold/ and must never enter any model context.

Usage:  python scripts/task_setup.py
"""

import json
import subprocess
import sys
from pathlib import Path

from datasets import load_dataset

INSTANCE_IDS = [
    "django__django-11099",
    "sympy__sympy-18087",
    "django__django-11019",
]

REPO_URLS = {
    "django/django": "https://github.com/django/django.git",
    "sympy/sympy": "https://github.com/sympy/sympy.git",
}

ROOT = Path(__file__).resolve().parent.parent
TASKS_DIR = ROOT / "tasks"

TREE_MAX_LINES = 2500  # cap the file listing in the context
EXCLUDE_PARTS = ("locale/", "doc/", "docs/", "examples/", "release/", ".ci/",
                 ".tx/", "data/")  # path prefixes/segments with no planning value


def sh(args, cwd=None):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"command failed: {' '.join(args)}\n{r.stderr}")
    return r.stdout


def wtext(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def main():
    print("loading SWE-bench Lite ...")
    ds = load_dataset("princeton-nlp/SWE-bench_Lite", split="test")
    by_id = {row["instance_id"]: row for row in ds}

    for iid in INSTANCE_IDS:
        if iid not in by_id:
            sys.exit(f"instance {iid} not found in SWE-bench Lite")
        row = by_id[iid]
        tdir = TASKS_DIR / iid
        repo_dir = tdir / "repo"
        gold_dir = tdir / "gold"
        gold_dir.mkdir(parents=True, exist_ok=True)

        # clone + checkout base commit
        if not repo_dir.exists():
            print(f"cloning {row['repo']} ...")
            sh(["git", "clone", REPO_URLS[row["repo"]], str(repo_dir)])
        sh(["git", "checkout", "-f", row["base_commit"]], cwd=repo_dir)
        sh(["git", "clean", "-fdx"], cwd=repo_dir)

        # gold artifacts: for grading reference only, never model-visible
        wtext(gold_dir / "patch.diff", row["patch"])
        wtext(gold_dir / "test_patch.diff", row["test_patch"])
        wtext(gold_dir / "tests.json", json.dumps(
                {
                    "FAIL_TO_PASS": json.loads(row["FAIL_TO_PASS"]),
                    "PASS_TO_PASS": json.loads(row["PASS_TO_PASS"]),
                },
                indent=2,
            ))

        # frozen model-visible context: .py files only, junk paths excluded
        tree = [
            p for p in sh(["git", "ls-files"], cwd=repo_dir).splitlines()
            if p.endswith(".py")
            and not any(seg in p for seg in EXCLUDE_PARTS)
        ]
        shown = tree[:TREE_MAX_LINES]
        omitted = len(tree) - len(shown)
        tree_block = "\n".join(shown) + (
            f"\n... ({omitted} more files omitted)" if omitted > 0 else ""
        )

        context = (
            f"# Task: {iid}\n\n"
            f"Repository: {row['repo']} @ {row['base_commit']}\n\n"
            f"## Problem statement\n\n{row['problem_statement']}\n\n"
            f"## Repository file listing\n\n```\n{tree_block}\n```\n\n"
            f"## Deliverable\n\n"
            f"A unified diff against the repository root that resolves the "
            f"problem. The diff must apply cleanly with `git apply`.\n"
        )
        wtext(tdir / "task_context.md", context)

        # metadata for downstream scripts
        (tdir / "meta.json").write_text(
            json.dumps(
                {
                    "instance_id": iid,
                    "repo": row["repo"],
                    "base_commit": row["base_commit"],
                    "version": row.get("version", ""),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"  {iid}: repo ready, context {len(context)} chars")

    print("done. Read both task_context.md files now and verify the problem "
          "statements match the selection rationale before generating graphs.")


if __name__ == "__main__":
    main()
