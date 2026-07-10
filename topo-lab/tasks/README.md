# Benchmark tasks

Task folders are regenerated locally, not committed. Each `repo/` is a full
upstream checkout and stays out of git.

## Generate

From `topo-lab/`:

```
python scripts/task_setup.py
```

The script pulls both instances from SWE-bench Lite, clones `django/django` and
`sympy/sympy` at their pinned base commits, writes the gold artifacts and a
frozen `task_context.md`, and fills `tasks/<instance_id>/`.

## Requirements

- Python with `datasets`: `pip install datasets`
- `git` on PATH
- Network access to GitHub and the Hugging Face Hub

## Layout produced

```
tasks/
  django__django-11099/
    repo/             full checkout at base commit d26b2424
    gold/             patch.diff, test_patch.diff, tests.json   (grading only, never in model context)
    task_context.md   frozen model-visible context
    meta.json
  sympy__sympy-18087/
    (same layout)
```

Instance IDs and base commits are pinned in `scripts/task_setup.py`. Re-running
the script is idempotent: existing `repo/` checkouts are reset to the base
commit rather than re-cloned.
