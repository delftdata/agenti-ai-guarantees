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


# ---- authored task for the paper's Figure 1 (providing_args removal) ----
# Not a SWE-bench instance. Same repo and base commit as django-11019, so the
# clone is taken from the local 11019 checkout when present (no network) and
# the .venv38 grading environment applies unchanged. The "gold" artifacts are
# authored: the test patch is a marker file creation (nothing to exclude from
# the mechanical diff - the shared test fixture the probe writes must stay
# graded), and the FAIL_TO_PASS list holds six real regression tests that
# pass at the base commit and gate the composed refactor.

FIG1_ID = "django__providing-args"
FIG1_BASE = "93e892bb645b16ebaf287beb5fe7f3ffe8d10408"

FIG1_MARKER_DIFF = """diff --git a/tests/dispatch/GOLD_MARKER.txt b/tests/dispatch/GOLD_MARKER.txt
new file mode 100644
--- /dev/null
+++ b/tests/dispatch/GOLD_MARKER.txt
@@ -0,0 +1 @@
+authored task: marker only, no gold test patch
"""

FIG1_TESTS = {
    "FAIL_TO_PASS": [
        "test_send (dispatch.tests.DispatcherTests)",
        "test_send_robust_success (dispatch.tests.DispatcherTests)",
        "test_cached_garbaged_collected (dispatch.tests.DispatcherTests)",
        "test_receiver_signal_list (dispatch.tests.ReceiverTestCase)",
        "test_save_signals (signals.tests.SignalTests)",
        "test_delete_signals (signals.tests.SignalTests)",
    ],
    "PASS_TO_PASS": [],
}

FIG1_STATEMENT = (
    "Remove the deprecated providing_args argument from Signal.\n\n"
    "django.dispatch.Signal accepts a providing_args list that is purely "
    "documentational: it is stored on the instance but never used by the "
    "dispatch machinery (Django ticket #31327 later deprecated and removed "
    "it upstream). Remove the parameter from Signal.__init__ in "
    "django/dispatch/dispatcher.py, including the stored providing_args "
    "attribute and the docstring references, and remove the argument from "
    "every Signal/ModelSignal construction site in django/db/models/"
    "signals.py, django/contrib/auth/signals.py, django/core/signals.py, "
    "django/db/backends/signals.py, django/test/signals.py, and the test "
    "fixture constructions in tests/dispatch/tests.py. All existing "
    "behavior must be preserved: the dispatch and signals test modules "
    "must continue to pass."
)


def setup_providing_args():
    tdir = TASKS_DIR / FIG1_ID
    repo_dir = tdir / "repo"
    gold_dir = tdir / "gold"
    gold_dir.mkdir(parents=True, exist_ok=True)

    if not repo_dir.exists():
        local = TASKS_DIR / "django__django-11019" / "repo"
        src = str(local) if local.is_dir() else REPO_URLS["django/django"]
        print(f"cloning django for {FIG1_ID} from {src} ...")
        sh(["git", "clone", src, str(repo_dir)])
    sh(["git", "config", "core.autocrlf", "false"], cwd=repo_dir)
    sh(["git", "config", "core.eol", "lf"], cwd=repo_dir)
    sh(["git", "checkout", "-f", FIG1_BASE], cwd=repo_dir)
    sh(["git", "clean", "-fdx"], cwd=repo_dir)

    # task-preparation commit: django.utils.translation imports
    # django.utils.autoreload at module level, and translation is on the
    # import path of django.test, so autoreload's single providing_args
    # construction site breaks every test run once Signal.__init__ drops the
    # parameter. Editing it inside the probe would put a 630-line whole-file
    # reproduction in one worker's write set; the removal is applied here
    # instead and committed, so it is part of the graded base state and
    # outside the probe's write set. Disclosed in the experiment doc.
    ar = repo_dir / "django" / "utils" / "autoreload.py"
    ar_text = ar.read_text(encoding="utf-8")
    ar_old = "file_changed = Signal(providing_args=['file_path', 'kind'])"
    if ar_old in ar_text:
        wtext(ar, ar_text.replace(ar_old, "file_changed = Signal()"))
        sh(["git", "-c", "user.email=topo-lab@local",
            "-c", "user.name=topo-lab", "commit", "-am",
            "task prep: remove providing_args from utils/autoreload"],
           cwd=repo_dir)

    wtext(gold_dir / "test_patch.diff", FIG1_MARKER_DIFF)
    wtext(gold_dir / "tests.json", json.dumps(FIG1_TESTS, indent=2))

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
        f"# Task: {FIG1_ID}\n\n"
        f"Repository: django/django @ {FIG1_BASE}\n\n"
        f"## Problem statement\n\n{FIG1_STATEMENT}\n\n"
        f"## Repository file listing\n\n```\n{tree_block}\n```\n\n"
        f"## Deliverable\n\n"
        f"A unified diff against the repository root that resolves the "
        f"problem. The diff must apply cleanly with `git apply`.\n"
    )
    wtext(tdir / "task_context.md", context)
    (tdir / "meta.json").write_text(
        json.dumps(
            {
                "instance_id": FIG1_ID,
                "repo": "django/django",
                "base_commit": FIG1_BASE,
                "version": "3.0",
                "authored": True,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"  {FIG1_ID}: repo ready, context {len(context)} chars")


def main():
    setup_providing_args()
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
