"""Narrate a run: turn trace.json into a wave-by-wave execution timeline
showing how state moves through the graph - what each node read (with the
byte count and the writer whose version it saw), what it wrote, and how
each commit landed (fresh write, cross-superstep handoff, or same-superstep
write conflict destroying a sibling's committed work).

Usage:
  python scripts/narrate.py <run-name> [<run-name> ...]
  python scripts/narrate.py django__django-11099.probe.parallel--agent-haiku--rep1
"""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"


def wave_of(trace):
    return {nid: i for i, wave in enumerate(trace["schedule"])
            for nid in wave}


def narrate(run_name: str) -> str:
    trace = json.loads((RUNS / run_name / "trace.json")
                       .read_text(encoding="utf-8"))
    waves = wave_of(trace)
    nodes = {n["node"]: n for n in trace["nodes"]}
    ow = trace.get("overwrite_events", [])

    lines = [f"# {run_name}",
             f"topology {trace['topology']}, agent {trace['agent']}, "
             f"wall {trace['wall_s']}s, cost ${trace['total_cost_usd']}",
             ""]

    # writer of each path as of the end of each wave, for commit narration
    last_writer = {}
    for i, wave in enumerate(trace["schedule"]):
        lines.append(f"## wave {i}: {', '.join(wave)}")
        for nid in wave:
            n = nodes[nid]
            for r in n["reads"]:
                lines.append(f"- {nid} reads {r['path']} "
                             f"({r['bytes']} bytes, version written by "
                             f"{r['writer']})")
            if n["missing_deps"]:
                lines.append(f"- {nid} starts WITHOUT its declared "
                             f"dependencies {n['missing_deps']} "
                             f"(premature consumption)")
            if n["status"] != "success":
                lines.append(f"- {nid} FAILS: {str(n['error'])[:120]}")
        lines.append(f"### commits at end of wave {i}")
        any_commit = False
        for nid in wave:
            n = nodes[nid]
            for path in n["files_written"]:
                any_commit = True
                prev = last_writer.get(path)
                if prev is None:
                    lines.append(f"- {nid} commits {path} (first write, "
                                 f"replaces seed)")
                elif waves[prev] == i:
                    lines.append(f"- {nid} commits {path}, DESTROYING "
                                 f"{prev}'s version committed in the same "
                                 f"superstep - write conflict (lost update)")
                else:
                    lines.append(f"- {nid} commits {path}, superseding "
                                 f"{prev}'s version from wave "
                                 f"{waves[prev]} - ordered handoff")
                last_writer[path] = nid
        if not any_commit:
            lines.append("- none")
        lines.append("")

    lines.append("## final workspace")
    if last_writer:
        for path, nid in sorted(last_writer.items()):
            lines.append(f"- {path}: {nid}'s version survives")
    else:
        lines.append("- no writes")
    # sanity: recorded overwrite events should match the narration
    lines.append("")
    lines.append(f"recorded overwrite events: {len(ow)} "
                 f"({sum(1 for e in ow if waves.get(e['prev_writer']) == waves.get(e['new_writer']))} "
                 f"same-superstep)")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    args = ap.parse_args()
    for name in args.runs:
        print(narrate(name))
        print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    main()
