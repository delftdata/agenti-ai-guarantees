"""Aggregate all real runs + grades into result tables injected into
docs/experiment.md.

Two generated blocks:
  RESULTS   - bracket experiment (django-11099, sympy-18087): the full
              configuration grid, coordination events per run, then the
              repetition study with its rationale
  RESULTS2  - gradient experiment (django-11019): per-topology means over
              repetitions, the identical-schedule controls, the per-run
              table, and condensed coordination events

Reads runs/*/trace.json (non-mock) and runs/grades.json (mechanical grade
at top level). Run scripts/grade.py first.

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
BEGIN2 = "<!-- RESULTS2:BEGIN -->"
END2 = "<!-- RESULTS2:END -->"
BEGIN3 = "<!-- RESULTS3:BEGIN -->"
END3 = "<!-- RESULTS3:END -->"

PHASE2_TASKS = {"django__django-11019"}
# authored paper-figure task: its runs go to the RESULTS3 block only
FIG1_TASK = "django__providing-args"
TOPO_ORDER = {"sequential": 0, "parallel": 1, "cut25": 2,
              "cut50": 3, "cut75": 4, "overparallel": 5}


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


def _wave(trace, nid):
    for i, w in enumerate(trace["schedule"]):
        if nid in w:
            return i
    return None


def load_rows():
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
        instance, harness, topo = t["graph"].removesuffix(".json").split(".")
        g = grades.get(d.name, {})
        rows.append({
            "name": d.name,
            "instance": instance,
            "task": instance.split("__")[-1] if "__" in instance else instance,
            "harness": harness, "topology": topo, "agent": t["agent"],
            "wall_s": t["wall_s"], "cost": t["total_cost_usd"],
            "node_failures": [n["node"] for n in t["nodes"]
                              if n["status"] != "success"],
            "premature": [n["node"] for n in t["nodes"] if n["missing_deps"]],
            "stale": stale_reads(t),
            "lost_updates": sum(
                1 for e in t.get("overwrite_events", [])
                if _wave(t, e["prev_writer"]) == _wave(t, e["new_writer"])),
            "tokens": sum(n.get("input_tokens", 0) + n.get("output_tokens", 0)
                          for n in t["nodes"]),
            "content": g.get("content"),
            "f2p": g.get("tests"),
            "test_frac": g.get("test_frac"),
            "resolved": g.get("resolved"),
        })
    rows.sort(key=lambda r: (r["task"], r["harness"], r["agent"],
                             TOPO_ORDER[r["topology"]], r["name"]))
    return rows


HEADER = ("| task | harness | agent | topology | wall (s) | cost ($) | "
          "tokens | node errors | premature consumptions | stale reads "
          "| write conflicts | content | f2p | resolved |\n"
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")

LEGEND = ("content: fraction of the task rubric present in the patch. "
          "f2p: FAIL_TO_PASS tests passing / total. resolved: every "
          "FAIL_TO_PASS test passes. tokens: input + output tokens summed "
          "over nodes, prompt-cache reads excluded. All grades apply to the "
          "mechanical deliverable (the workspace diff).")

REP_RATIONALE = (
    "A single run per configuration cannot distinguish behavior inherent "
    "to that configuration from sampling noise: the agent is sampled at "
    "nonzero temperature. One configuration was rerun ten times - the "
    "weak-harness django decomposition, over-parallel rendering, weak "
    "agent, chosen as the cheapest cell with the richest "
    "coordination-event set. Schedule-derived quantities (which files were "
    "read stale, which dependencies were consumed prematurely) are "
    "expected to repeat exactly; model-dependent quantities may vary.")


def _res(v):
    return {True: "yes", False: "no"}.get(v, "-")


def _mean(vals, digits=3):
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), digits) if vals else None


def table(rows):
    lines = [HEADER]
    for r in rows:
        lines.append(
            f"| {r['task']} | {r['harness']} | {r['agent']} | {r['topology']} "
            f"| {r['wall_s']} | {r['cost']} | {r['tokens']} "
            f"| {len(r['node_failures'])} | {len(r['premature'])} "
            f"| {len(r['stale'])} | {r['lost_updates']} "
            f"| {r['content']} | {r['f2p']} | {_res(r['resolved'])} |")
    return "\n".join(lines)


def event_strings(r):
    events = []
    for e in r["stale"]:
        events.append(f"stale read: `{e['reader']}` read `{e['path']}` "
                      f"while `{e['writer']}` rewrote it in the same superstep")
    for nid in r["premature"]:
        events.append(f"premature consumption at `{nid}`")
    for nid in r["node_failures"]:
        events.append(f"node error at `{nid}`")
    return events


def events_block(rows):
    lines = []
    for r in rows:
        events = event_strings(r)
        if events:
            lines.append(f"**{r['task']} / {r['harness']} harness / "
                         f"{r['agent']} agent / {r['topology']}**")
            lines += [f"- {e}" for e in events]
            lines.append("")
    return "\n".join(lines)


def events_condensed(rows):
    """Group runs by (topology, event signature); print each group once."""
    groups = {}
    for r in sorted(rows, key=lambda r: TOPO_ORDER[r["topology"]]):
        key = (TOPO_ORDER[r["topology"]], r["topology"],
               tuple(sorted(event_strings(r))))
        groups.setdefault(key, []).append(r["name"])
    lines = []
    for (_, topo, events), names in sorted(groups.items()):
        if not events:
            lines.append(f"**{topo}** ({len(names)} runs) - no events")
            lines.append("")
            continue
        lines.append(f"**{topo}** ({len(names)} runs, identical event set)"
                     if len(names) > 1 else f"**{topo}** (1 run)")
        lines += [f"- {e}" for e in sorted(events)]
        lines.append("")
    return "\n".join(lines)


def gradient_aggregate(reps):
    """Per-topology means over repetitions."""
    header = ("| topology | runs | wall (s) | cost ($) | tokens | "
              "node errors | "
              "premature consumptions | stale reads | write conflicts | "
              "content | f2p frac | resolved |\n"
              "|---|---|---|---|---|---|---|---|---|---|---|---|")
    lines = [header]
    topos = sorted({r["topology"] for r in reps},
                   key=lambda t: TOPO_ORDER[t])
    for topo in topos:
        rs = [r for r in reps if r["topology"] == topo]
        n = len(rs)
        res = sum(1 for r in rs if r["resolved"])
        lines.append(
            f"| {topo} | {n} "
            f"| {_mean([r['wall_s'] for r in rs], 1)} "
            f"| {_mean([r['cost'] for r in rs], 4)} "
            f"| {_mean([r['tokens'] for r in rs], 0)} "
            f"| {_mean([len(r['node_failures']) for r in rs], 1)} "
            f"| {_mean([len(r['premature']) for r in rs], 1)} "
            f"| {_mean([len(r['stale']) for r in rs], 1)} "
            f"| {_mean([r['lost_updates'] for r in rs], 1)} "
            f"| {_mean([r['content'] for r in rs], 2)} "
            f"| {_mean([r['test_frac'] for r in rs], 3)} "
            f"| {res}/{n} |")
    return "\n".join(lines)


def controls_paragraph(reps):
    pairs = [("parallel", "cut25"), ("cut50", "cut75")]
    parts = []
    for a, b in pairs:
        fa = _mean([r["test_frac"] for r in reps if r["topology"] == a])
        fb = _mean([r["test_frac"] for r in reps if r["topology"] == b])
        if fa is None or fb is None:
            continue
        parts.append(f"{a} vs {b}: mean f2p {fa} vs {fb}")
    if not parts:
        return ""
    return ("Identical-schedule controls (pairs whose effective schedules "
            "coincide; their distributions must be indistinguishable if "
            "the rig is sound): " + "; ".join(parts) + ".")


PROBE_EXPLANATION = (
    "The write-conflict probe isolates the coordination mechanism from "
    "worker capability. Its plan is authored rather than harness-generated, "
    "and disclosed as such: the reference fix touches two independent "
    "regions of one small file, each region assigned to one worker whose "
    "instruction contains the exact edit, so every individual worker action "
    "is correct by construction and capability is held at ceiling. The only "
    "variable left is the schedule. Sequentially, each worker receives the "
    "file with the previous edit already present and preserves it, so the "
    "edits compose. In parallel, both workers read the same snapshot and "
    "each commits a complete file containing only its own edit; the store "
    "keeps the last write and the other worker's committed correct work is "
    "destroyed - the lost update of concurrency-control theory, recorded "
    "as a write conflict in the failure vocabulary. The probe "
    "targets django-11099 because its file is small enough that whole-file "
    "reproduction is error-free, removing copy fidelity as a confound.")

ORDERED_EXPLANATION = (
    "The ordered arm applies the coordination primitive to the failing "
    "schedule. Exactly one thing changes relative to the unordered probe: "
    "the plan declares a single dependency edge between the two writers "
    "(fix_unicode depends on fix_ascii). Instructions, agent model, "
    "renderer, and grading are identical. The renderer turns the declared "
    "edge into an ordering constraint, so the second writer starts only "
    "after the first has committed, receives the file with the first edit "
    "already present, and preserves it - the write sets no longer overlap "
    "within a superstep, so the lost update cannot occur. This is the "
    "standard concurrency-control remedy for a write-write conflict, "
    "applied statically: serialize exactly the conflicting pair and "
    "nothing else.")


def probe_analysis(reps):
    lines = []
    arms = [("probe", "sequential", "sequential (implicit total order)"),
            ("probe", "parallel", "parallel, unordered writers"),
            ("probeordered", "parallel",
             "parallel, one declared ordering edge (the primitive)")]
    for h, topo, label in arms:
        rs = [r for r in reps if r["harness"] == h and r["topology"] == topo]
        if not rs:
            continue
        n = len(rs)
        res = sum(1 for r in rs if r["resolved"])
        contents = sorted({r["content"] for r in rs})
        stales = sorted({len(r["stale"]) for r in rs})
        lost = sorted({r["lost_updates"] for r in rs})
        lines.append(f"- {label}: {res}/{n} resolved; content values "
                     f"{contents}; same-superstep stale reads per run "
                     f"{stales}; write conflicts per run {lost}.")
    lines.append("")
    lines.append(
        "The outcome flip is schedule-derived: every unordered parallel "
        "repetition lost the same edit to the same last-write-wins conflict "
        "while the sampled worker outputs varied. The ordered arm shows the "
        "repair: one declared dependency between the conflicting writers "
        "restores resolution. In this minimal probe the conflicting pair is "
        "the entire graph, so serializing it recovers the sequential "
        "schedule; the wall-time case for parallelism rests on the gradient "
        "runs, where non-conflicting work parallelizes with no accuracy "
        "loss under the same state discipline.")
    return "\n".join(lines)


FIG1_ORDERED_LABEL = ("parallel, conflicting pair ordered "
                      "(t2_auth_signals after t1_db_signals)")


def fig1_analysis(reps):
    lines = []
    arms = [("probe", "sequential", "sequential (implicit total order)"),
            ("probe", "parallel", "parallel, unordered writers"),
            ("probeordered", "parallel", FIG1_ORDERED_LABEL)]
    for h, topo, label in arms:
        rs = [r for r in reps if r["harness"] == h and r["topology"] == topo]
        if not rs:
            continue
        n = len(rs)
        res = sum(1 for r in rs if r["resolved"])
        contents = sorted({r["content"] for r in rs})
        f2ps = sorted({r["f2p"] for r in rs})
        stales = sorted({len(r["stale"]) for r in rs})
        lost = sorted({r["lost_updates"] for r in rs})
        lines.append(f"- {label}: {res}/{n} resolved; f2p values {f2ps}; "
                     f"content values {contents}; same-superstep stale reads "
                     f"per run {stales}; write conflicts per run {lost}.")
    return "\n".join(lines)


def main():
    rows = load_rows()
    p1 = [r for r in rows if r["instance"] not in PHASE2_TASKS
          and r["instance"] != FIG1_TASK
          and not r["harness"].startswith("probe")]
    p2 = [r for r in rows if r["instance"] != FIG1_TASK
          and (r["instance"] in PHASE2_TASKS
               or r["harness"].startswith("probe"))]
    p3 = [r for r in rows if r["instance"] == FIG1_TASK]

    # ---- phase 1: bracket ----
    grid = [r for r in p1 if not re.search(r"--rep\d+$", r["name"])]
    reps = [r for r in p1 if re.search(r"--rep\d+$", r["name"])]
    parts = ["### Run grid",
             "",
             LEGEND,
             "",
             table(grid),
             "", "### Coordination events by run",
             "", events_block(grid)]
    if reps:
        resolved = sorted({_res(r["resolved"]) for r in reps})
        contents = sorted({r["content"] for r in reps})
        sig = {}
        for r in reps:
            key = (len(r["stale"]), len(r["premature"]),
                   len(r["node_failures"]))
            sig[key] = sig.get(key, 0) + 1
        parts += [f"### Repetition study ({len(reps)} runs of "
                  f"{reps[0]['task']} / {reps[0]['harness']} harness / "
                  f"{reps[0]['topology']}, {reps[0]['agent']} agent)",
                  "",
                  REP_RATIONALE,
                  "",
                  table(reps),
                  "",
                  f"Determinism summary: coordination event signatures "
                  f"(stale, premature, node errors) and counts: {sig}; "
                  f"resolved values {resolved}; content values {contents}."]
    block1 = BEGIN + "\n\n" + "\n".join(parts) + "\n\n" + END

    # ---- phase 2: gradient + probe ----
    g2 = [r for r in p2 if not r["harness"].startswith("probe")]
    pr = [r for r in p2 if r["harness"].startswith("probe")]
    g_reps = [r for r in g2 if re.search(r"--rep\d+$", r["name"])]
    probe_reps = [r for r in pr if re.search(r"--rep\d+$", r["name"])]
    parts2 = []
    if g_reps:
        parts2 += ["### Gradient runs",
                   "",
                   LEGEND,
                   "",
                   table(g_reps),
                   "", "### Coordination events by topology",
                   "", events_condensed(g_reps),
                   "", "### Means per topology",
                   "", gradient_aggregate(g_reps)]
        ctrl = controls_paragraph(g_reps)
        if ctrl:
            parts2 += ["", ctrl]
    if probe_reps:
        base = [r for r in probe_reps if r["harness"] == "probe"]
        ordered = [r for r in probe_reps if r["harness"] == "probeordered"]
        parts2 += ["", "### Write-conflict probe",
                   "", PROBE_EXPLANATION,
                   "", table(base)]
        if ordered:
            parts2 += ["", "#### Ordered arm - the primitive applied",
                       "", ORDERED_EXPLANATION,
                       "", table(ordered)]
        parts2 += ["", probe_analysis(probe_reps)]
    if not parts2:
        parts2 = ["(no gradient runs recorded yet)"]
    block2 = BEGIN2 + "\n\n" + "\n".join(parts2) + "\n\n" + END2

    # ---- phase 3: paper-figure probe (providing_args removal) ----
    p3_reps = [r for r in p3 if re.search(r"--rep\d+$", r["name"])]
    parts3 = []
    if p3_reps:
        base3 = [r for r in p3_reps if r["harness"] == "probe"]
        ordered3 = [r for r in p3_reps if r["harness"] == "probeordered"]
        parts3 += ["### Runs", "", LEGEND, "", table(base3)]
        if ordered3:
            parts3 += ["", "#### Ordered arm", "", table(ordered3)]
        parts3 += ["", fig1_analysis(p3_reps)]
    else:
        parts3 = ["(no runs recorded yet)"]
    block3 = BEGIN3 + "\n\n" + "\n".join(parts3) + "\n\n" + END3

    doc = DOC.read_text(encoding="utf-8")
    for begin, end, block in ((BEGIN, END, block1), (BEGIN2, END2, block2),
                              (BEGIN3, END3, block3)):
        if begin not in doc or end not in doc:
            raise SystemExit(f"experiment.md is missing the {begin} markers")
        doc = re.sub(re.escape(begin) + r".*?" + re.escape(end), block,
                     doc, flags=re.DOTALL)
    DOC.write_text(doc, encoding="utf-8")
    print(f"summarized {len(rows)} runs into docs/experiment.md "
          f"({len(grid)} bracket grid, {len(reps)} bracket repetition, "
          f"{len(p2)} gradient, {len(p3)} figure-1 probe)")


if __name__ == "__main__":
    main()
