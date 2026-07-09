"""Grade completed runs.

Tier 1 (always): model patch applies at base commit; gold test patch applies
on top of it. Tier 2 (--python <exe>): run the instance's FAIL_TO_PASS tests
in a temporary worktree using the given interpreter (needs a Python version
contemporary with the repos, e.g. 3.8, with pytest/pytz/sqlparse/asgiref).

Usage:
  python scripts/grade.py                    # tier 1, all non-mock runs
  python scripts/grade.py --python C:\\py38\\python.exe   # tier 1 + 2
"""

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"

TEST_CMDS = {
    "django__django-11099": ["tests/runtests.py", "auth_tests.test_validators",
                             "--parallel", "1"],
    "sympy__sympy-18087": ["-m", "pytest",
                           "sympy/core/tests/test_exprtools.py::test_Factors",
                           "sympy/simplify/tests/test_fu.py::test_fu",
                           "-p", "no:cacheprovider", "-q"],
}


def sh(args, cwd=None):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def grade_run(run_dir: Path, python_exe: str | None):
    task = run_dir.name.split(".")[0]
    repo = ROOT / "tasks" / task / "repo"
    gold_tests = ROOT / "tasks" / task / "gold" / "test_patch.diff"
    patch = run_dir / "patch.diff"
    row = {"run": run_dir.name, "patch_applies": False,
           "test_patch_applies": False, "normalized": False, "tests": "n/a"}
    if not patch.exists() or not patch.read_text(encoding="utf-8").strip():
        row["tests"] = "no patch"
        return row
    raw = patch.read_text(encoding="utf-8").strip()
    norm = re.sub(r"^```[a-z]*\s*\n", "", raw)
    norm = re.sub(r"\n```\s*$", "", norm)
    if not norm.endswith("\n"):
        norm += "\n"
    row["normalized"] = norm.strip() != raw
    apply_path = run_dir / "patch.normalized.diff"
    apply_path.write_text(norm, encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        wt = Path(tmp) / "wt"
        r = sh(["git", "worktree", "add", "--detach", str(wt)], cwd=repo)
        if r.returncode != 0:
            row["tests"] = f"worktree failed: {r.stderr.strip()[:80]}"
            return row
        try:
            r = sh(["git", "apply", "--whitespace=nowarn",
                    str(apply_path.resolve())], cwd=wt)
            row["patch_applies"] = r.returncode == 0
            if not row["patch_applies"]:
                row["apply_error"] = r.stderr.strip()[:200]
                return row
            r = sh(["git", "apply", "--whitespace=nowarn",
                    str(gold_tests.resolve())], cwd=wt)
            row["test_patch_applies"] = r.returncode == 0
            if not row["test_patch_applies"]:
                row["apply_error"] = r.stderr.strip()[:200]
                return row
            if python_exe:
                cmd = [python_exe] + TEST_CMDS[task]
                r = sh(cmd, cwd=wt)
                row["tests"] = "pass" if r.returncode == 0 else "fail"
                (run_dir / "test_output.txt").write_text(
                    r.stdout + "\n--- stderr ---\n" + r.stderr,
                    encoding="utf-8")
        finally:
            sh(["git", "worktree", "remove", "--force", str(wt)], cwd=repo)
            sh(["git", "worktree", "prune"], cwd=repo)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--python", default=None,
                    help="interpreter for tier-2 test execution")
    ap.add_argument("--runs", nargs="*", default=None,
                    help="specific run dir names; default: all non-mock")
    args = ap.parse_args()

    if args.runs:
        dirs = [RUNS / r for r in args.runs]
    else:
        dirs = sorted(d for d in RUNS.iterdir()
                      if d.is_dir() and "--mock" not in d.name)
    rows = [grade_run(d, args.python) for d in dirs]
    (RUNS / "grades.json").write_text(json.dumps(rows, indent=2),
                                      encoding="utf-8")
    w = max(len(r["run"]) for r in rows) if rows else 10
    print(f"{'run':<{w}}  patch  test_patch  tests")
    for r in rows:
        print(f"{r['run']:<{w}}  {str(r['patch_applies']):<5}  "
              f"{str(r['test_patch_applies']):<10}  {r['tests']}")
    print(f"\nwrote runs/grades.json")


if __name__ == "__main__":
    main()
