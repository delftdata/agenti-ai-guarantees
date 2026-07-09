"""Render each harness decomposition into three execution topologies and
inject Mermaid diagrams into docs/experiment.md.

Inputs:  graphs/<task>.<model>.decomp.txt   (raw Workbench output)
Outputs: graphs/rendered/<task>.<model>.<topology>.json  (executable graph)
         graphs/rendered/<task>.<model>.<topology>.mmd   (Mermaid source)
         docs/experiment.md                               (diagrams injected
         between the TOPOLOGIES markers)

Usage:  python scripts/render_topologies.py
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GRAPHS = ROOT / "graphs"
RENDERED = GRAPHS / "rendered"
DOC = ROOT / "docs" / "experiment.md"

DECOMPS = [
    ("django__django-11099", "opus"),
    ("django__django-11099", "haiku"),
    ("sympy__sympy-18087", "opus"),
    ("sympy__sympy-18087", "haiku"),
]
TOPOLOGIES = ["sequential", "parallel", "overparallel"]

BEGIN = "<!-- TOPOLOGIES:BEGIN -->"
END = "<!-- TOPOLOGIES:END -->"


def load_decomp(path: Path) -> dict:
    """Parse raw model output. Repairs are logged, never silent."""
    text = path.read_text(encoding="utf-8")
    repairs = []
    stripped = re.sub(r"</?json>", "", text)
    if stripped != text:
        repairs.append("removed <json> wrapper")
    text = stripped
    stripped = re.sub(r"```(?:json)?", "", text)
    if stripped != text:
        repairs.append("removed markdown fences")
    text = stripped.strip()
    # invalid JSON escapes like \w \A \Z from raw regex strings.
    # Consume escape pairs atomically so valid \\ sequences are untouched.
    def _fix(m):
        c = m.group(1)
        return m.group(0) if c in '"\\/bfnrtu' else "\\\\" + c
    fixed = re.sub(r"\\(.)", _fix, text, flags=re.DOTALL)
    if fixed != text:
        repairs.append("escaped invalid backslash sequences")
    text = fixed
    decomp = json.loads(text)
    if repairs:
        print(f"  {path.name}: repaired ({'; '.join(repairs)})")
    return decomp


def validate(decomp: dict, name: str):
    nodes = decomp["nodes"]
    ids = [n["id"] for n in nodes]
    if len(ids) != len(set(ids)):
        sys.exit(f"{name}: duplicate node ids")
    idset = set(ids)
    if decomp["final_node"] not in idset:
        sys.exit(f"{name}: final_node not among nodes")
    for n in nodes:
        for d in n["deps"]:
            if d not in idset:
                sys.exit(f"{name}: node {n['id']} deps on unknown {d}")
    # acyclicity via Kahn
    indeg = {i: 0 for i in ids}
    for n in nodes:
        for _ in n["deps"]:
            indeg[n["id"]] += 1
    ready = sorted(i for i in ids if indeg[i] == 0)
    seen = 0
    deps_of = {n["id"]: set(n["deps"]) for n in nodes}
    done = set()
    while ready:
        cur = ready.pop(0)
        done.add(cur)
        seen += 1
        for n in nodes:
            if cur in deps_of[n["id"]] and n["id"] not in done:
                if deps_of[n["id"]] <= done and n["id"] not in ready:
                    ready.append(n["id"])
        ready.sort()
    if seen != len(ids):
        sys.exit(f"{name}: dependency cycle detected")


def schedule(decomp: dict, topology: str):
    """Waves of node ids. Deterministic: lexicographic tie-break."""
    nodes = decomp["nodes"]
    deps_of = {n["id"]: set(n["deps"]) for n in nodes}
    ids = sorted(deps_of)
    final = decomp["final_node"]
    if topology == "sequential":
        waves, done = [], set()
        while len(done) < len(ids):
            nxt = min(i for i in ids if i not in done and deps_of[i] <= done)
            waves.append([nxt])
            done.add(nxt)
        return waves
    if topology == "parallel":
        level = {}
        def lv(i):
            if i not in level:
                level[i] = 1 + max((lv(d) for d in deps_of[i]), default=-1)
            return level[i]
        for i in ids:
            lv(i)
        waves = []
        for w in range(max(level.values()) + 1):
            waves.append(sorted(i for i in ids if level[i] == w))
        return waves
    if topology == "overparallel":
        first = sorted(i for i in ids if i != final)
        return [first, [final]] if first else [[final]]
    sys.exit(f"unknown topology {topology}")


def mermaid(decomp: dict, topology: str, waves) -> str:
    nodes = decomp["nodes"]
    final = decomp["final_node"]
    lines = ["flowchart TD"]
    for n in nodes:
        lines.append(f"    {n['id']}[{n['id']}]")
    if topology == "sequential":
        order = [w[0] for w in waves]
        for a, b in zip(order, order[1:]):
            lines.append(f"    {a} --> {b}")
    elif topology == "parallel":
        for n in nodes:
            for d in n["deps"]:
                lines.append(f"    {d} --> {n['id']}")
    else:  # overparallel: ordering = everyone before final; cut deps dotted
        for n in nodes:
            if n["id"] != final:
                lines.append(f"    {n['id']} --> {final}")
            for d in n["deps"]:
                if n["id"] != final:
                    lines.append(f"    {d} -.-> {n['id']}")
    lines.append(f"    style {final} stroke-width:3px")
    return "\n".join(lines)


def main():
    RENDERED.mkdir(exist_ok=True)
    sections = []
    for task, model in DECOMPS:
        raw = GRAPHS / f"{task}.{model}.decomp.txt"
        decomp = load_decomp(raw)
        name = f"{task}.{model}"
        validate(decomp, name)
        guards = [n["id"] for n in decomp["nodes"] if n.get("guard")]
        print(f"  {name}: {len(decomp['nodes'])} nodes, "
              f"{'guards: ' + ','.join(guards) if guards else 'no guards'}")
        sections.append(f"### {task} - {model} harness\n")
        for topo in TOPOLOGIES:
            waves = schedule(decomp, topo)
            out = dict(decomp)
            out["topology"] = topo
            out["schedule"] = waves
            jpath = RENDERED / f"{task}.{model}.{topo}.json"
            jpath.write_text(
                json.dumps(out, indent=2), encoding="utf-8")
            mmd = mermaid(decomp, topo, waves)
            (RENDERED / f"{task}.{model}.{topo}.mmd").write_text(
                mmd, encoding="utf-8")
            width = max(len(w) for w in waves)
            sections.append(
                f"**{topo}** - {len(waves)} waves, max width {width}\n\n"
                f"```mermaid\n{mmd}\n```\n")
    block = BEGIN + "\n\n" + "\n".join(sections) + "\n" + END
    doc = DOC.read_text(encoding="utf-8")
    if BEGIN not in doc or END not in doc:
        sys.exit("experiment.md is missing the TOPOLOGIES markers")
    doc = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END), block,
                 doc, flags=re.DOTALL)
    DOC.write_text(doc, encoding="utf-8")
    print(f"wrote {len(DECOMPS) * len(TOPOLOGIES)} rendered graphs, "
          f"updated {DOC.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
