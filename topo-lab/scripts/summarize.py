"""Aggregate all real runs + grades into result tables injected into
docs/experiment.md between the RESULTS markers.

Reads runs/*/trace.json (non-mock) and runs/grades.json.
Run scripts/grade.py first.

Usage:  python scripts/summarize.py
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"
DOC = ROOT / "docs" / "experiment.md"
BEGIN = "<!-- RESULTS:BEGIN -->"
END = "<!-- RESULTS:END -->"


def stale_reads(trace):
    """Reads of a path that a same-superstep sibling rewrote."""
    wave_of = {}
    for i, wave in enumerate(trace["schedule"]):
        for nid in wave:
            wave_of[nid] = i
    writes_by_node = {n["node"]: set(n["files_written"]) for n in trace["nodes"]}
    events = []
    for n in trace["nodes"]:
        for r in n["reads"]:
            for sib, w in writes_by_node.items():
                if (sib != n["node"] and r["path"] in w
                        and wave_of.get(sib) == wave_of.get(n["node"])):
                    events.append({"reader": n["node"], "writer": sib,
                                   "path": r["path"]})
    return events


def main():
    grades = {}
    gfile = RUNS / "grades.json"
    if gfile.exists():
        for row in json.loads(gfile.read_text(encoding="utf-8")):
            grades[row["run"]] = row

    rows = []
    for d in sorted(RUNS.iterdir()):
        tfile = d / "trace.json"
        if not d.is_dir() or "--mock" in d.name or not tfile.exists():
            continue
        t = json.loads(tfile.read_text(encoding="utf-8"))
        task, harness, topo = t["graph"].removesuffix(".json").split(".")
        node_failures = [n["node"] for n in t["nodes"] if n["status"] != "success"]
        premature = [n["node"] for n in t["nodes"] if n["missing_deps"]]
        stale = stale_reads(t)
        g = grades.get(d.name, {})
        rows.append({
            "task": "django" if task.startswith("django") else "sympy",
            "harness": harness, "topology": topo, "agent": t["agent"],
            "wall_s": t["wall_s"],
            "cost": t["total_cost_usd"],
            "node_failures": node_failures,
            "premature": premature,
            "stale": stale,
            "overwrites": t["overwrite_events"],
            "applies": g.get("patch_applies"),
            "test_patch": g.get("test_patch_applies"),
            "normalized": g.get("normalized"),
        })

    topo_order = {"sequential": 0, "parallel": 1, "overparallel": 2}
    rows.sort(key=lambda r: (r["task"], r["harness"], r["agent"],
                             topo_order[r["topology"]]))

    lines = ["### Run outcomes", "",
             "| task | harness | agent | topology | wall (s) | cost ($) | "
             "node errors | premature | stale reads | applies | gold tests apply |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(
            f"| {r['task']} | {r['harness']} | {r['agent']} | {r['topology']} "
            f"| {r['wall_s']} | {r['cost']} "
            f"| {len(r['node_failures'])} | {len(r['premature'])} "
            f"| {len(r['stale'])} | {r['applies']} | {r['test_patch']} |")

    lines += ["", "### Coordination events by run", ""]
    for r in rows:
        events = []
        for e in r["stale"]:
            events.append(f"stale read: `{e['reader']}` read `{e['path']}` "
                          f"while `{e['writer']}` rewrote it in the same superstep")
        for nid in r["premature"]:
            events.append(f"premature consumption at `{nid}`")
        for e in r["overwrites"]:
            events.append(f"overwrite of `{e['path']}`: `{e['prev_writer']}` "
                          f"then `{e['new_writer']}`")
        for nid in r["node_failures"]:
            events.append(f"node error at `{nid}`")
        if events:
            lines.append(f"**{r['task']} / {r['harness']} harness / "
                         f"{r['agent']} agent / {r['topology']}**")
            lines += [f"- {e}" for e in events]
            lines.append("")

    block = BEGIN + "\n\n" + "\n".join(lines) + "\n\n" + END
    doc = DOC.read_text(encoding="utf-8")
    if BEGIN not in doc:
        doc = doc.rstrip() + f"\n\n## Results\n\n{block}\n\n## Analysis\n\n(to be written from the joined tables)\n"
    else:
        doc = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END), block,
                     doc, flags=re.DOTALL)
    DOC.write_text(doc, encoding="utf-8")
    print(f"summarized {len(rows)} runs into docs/experiment.md")


if __name__ == "__main__":
    main()
