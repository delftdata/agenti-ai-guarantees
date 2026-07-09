"""Execute a rendered topology graph on LangGraph with real or mock agents.

Usage:
  python scripts/execute_graph.py graphs/rendered/<graph>.json --agent haiku --mock
  python scripts/execute_graph.py graphs/rendered/<graph>.json --agent opus

Artifacts per run, under runs/<graph>--agent-<model>[--mock]/ :
  trace.json    per-node record: reads (with version writer), missing deps,
                tokens, cost, wall time, status
  patch.diff    raw output of the final node
  nodes/<id>.txt  raw output of every node
  files_after/  workspace state at end of run
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Annotated, TypedDict

from langgraph.graph import StateGraph, START, END

ROOT = Path(__file__).resolve().parent.parent
MODELS = {"opus": "claude-opus-4-8", "haiku": "claude-haiku-4-5"}
# USD per MTok: (input, output); cache reads billed at 10% of input
RATES = {"opus": (5.0, 25.0), "haiku": (1.0, 5.0)}
MAX_TOKENS = 32000

FILE_BLOCK = re.compile(r"===FILE: (.*?)===\n(.*?)===END===", re.DOTALL)

OVERWRITE_EVENTS = []  # (path, prev_writer, new_writer)


def files_reducer(current: dict, update: dict) -> dict:
    merged = dict(current)
    for path, entry in update.items():
        prev = merged.get(path)
        if prev and prev["writer"] not in ("__seed__", entry["writer"]):
            OVERWRITE_EVENTS.append(
                {"path": path, "prev_writer": prev["writer"],
                 "new_writer": entry["writer"]})
        merged[path] = entry
    return merged


def dict_merge(current: dict, update: dict) -> dict:
    return {**current, **update}


class RunState(TypedDict):
    files: Annotated[dict, files_reducer]
    node_outputs: Annotated[dict, dict_merge]
    trace: Annotated[list, lambda a, b: a + b]


def build_worker_prompt(spec, state, task_context, is_final):
    parts = []
    missing = []
    reads_meta = []
    for path in spec["reads"]:
        entry = state["files"].get(path)
        if entry is None:
            reads_meta.append({"path": path, "bytes": 0, "writer": None})
            parts.append(f"[file not found in workspace: {path}]")
            continue
        reads_meta.append({"path": path, "bytes": len(entry["content"]),
                           "writer": entry["writer"]})
        parts.append(f"=== CURRENT CONTENTS OF {path} ===\n{entry['content']}\n=== END OF {path} ===")
    for dep in spec["deps"]:
        out = state["node_outputs"].get(dep)
        if out is None:
            missing.append(dep)
        else:
            parts.append(f"=== OUTPUT OF UPSTREAM NODE {dep} ===\n{out['text']}\n=== END OF {dep} ===")
    if is_final:
        contract = ("OUTPUT CONTRACT: output a single raw unified diff against "
                    "the repository root, applying cleanly with git apply. "
                    "No prose, no fences, no markers.")
    elif spec["writes"]:
        contract = ("OUTPUT CONTRACT: for EVERY file you modify or create, output\n"
                    "===FILE: <repo/relative/path>===\n<complete new file contents>\n===END===\n"
                    "You may add brief analysis text outside the blocks.")
    else:
        contract = "OUTPUT CONTRACT: output your analysis as plain text."
    user = "\n\n".join(parts + [f"YOUR INSTRUCTION:\n{spec['instruction']}", contract])
    return user, missing, reads_meta


def make_node(spec, task_context, agent, mock, is_final, run_dir):
    def node_fn(state: RunState):
        t0 = time.time()
        user, missing, reads_meta = build_worker_prompt(
            spec, state, task_context, is_final)
        status, error = "success", None
        usage = {"input_tokens": 0, "output_tokens": 0, "cache_read": 0}
        if mock:
            if is_final:
                text = "diff --git a/MOCK b/MOCK\n--- a/MOCK\n+++ b/MOCK\n"
            elif spec["writes"]:
                blocks = []
                for p in spec["writes"]:
                    base = state["files"].get(p, {"content": ""})["content"]
                    blocks.append(f"===FILE: {p}===\n{base}# MOCK EDIT by {spec['id']}\n===END===")
                text = "\n".join(blocks)
            else:
                text = f"[mock analysis from {spec['id']}]"
            usage["input_tokens"] = (len(task_context) + len(user)) // 4
            usage["output_tokens"] = len(text) // 4
        else:
            import anthropic
            client = anthropic.Anthropic()
            try:
                with client.messages.stream(
                    model=MODELS[agent],
                    max_tokens=MAX_TOKENS,
                    system=[{"type": "text", "text": task_context,
                             "cache_control": {"type": "ephemeral"}}],
                    messages=[{"role": "user", "content": user}],
                ) as stream:
                    text = "".join(stream.text_stream)
                    resp = stream.get_final_message()
                usage["input_tokens"] = resp.usage.input_tokens
                usage["output_tokens"] = resp.usage.output_tokens
                usage["cache_read"] = getattr(
                    resp.usage, "cache_read_input_tokens", 0) or 0
            except Exception as e:  # node error, graph continues
                text, status, error = "", "failure", repr(e)
        writes_update = {}
        if spec["writes"] and status == "success" and not is_final:
            found = {p: c for p, c in FILE_BLOCK.findall(text)}
            for p in spec["writes"]:
                if p in found:
                    writes_update[p] = {"writer": spec["id"], "content": found[p]}
            if not found:
                status = "failure"
                error = "declared writes but no parseable FILE blocks in output"
        (run_dir / "nodes").mkdir(exist_ok=True, parents=True)
        (run_dir / "nodes" / f"{spec['id']}.txt").write_text(text, encoding="utf-8")
        inp, out = RATES[agent]
        cost = (usage["input_tokens"] * inp + usage["output_tokens"] * out
                + usage["cache_read"] * inp * 0.1) / 1e6
        record = {
            "node": spec["id"], "wall_s": round(time.time() - t0, 2),
            "reads": reads_meta, "missing_deps": missing,
            "input_tokens": usage["input_tokens"],
            "cache_read_tokens": usage["cache_read"],
            "output_tokens": usage["output_tokens"],
            "cost_usd": round(cost, 5),
            "status": status, "error": error,
            "files_written": sorted(writes_update),
        }
        return {"files": writes_update,
                "node_outputs": {spec["id"]: {"text": text, "status": status}},
                "trace": [record]}
    return node_fn


def build_graph(graph_spec, task_context, agent, mock, run_dir):
    final = graph_spec["final_node"]
    topo = graph_spec["topology"]
    g = StateGraph(RunState)
    specs = {n["id"]: n for n in graph_spec["nodes"]}
    for nid, spec in specs.items():
        g.add_node(nid, make_node(spec, task_context, agent, mock,
                                  nid == final, run_dir))
    if topo == "sequential":
        order = [w[0] for w in graph_spec["schedule"]]
        g.add_edge(START, order[0])
        for a, b in zip(order, order[1:]):
            g.add_edge(a, b)
        g.add_edge(order[-1], END)
    elif topo == "parallel":
        for nid, spec in specs.items():
            if not spec["deps"]:
                g.add_edge(START, nid)
            else:
                # join: run once, after ALL deps - a list is one edge,
                # separate add_edge calls would re-trigger the node per dep
                g.add_edge(sorted(spec["deps"]), nid)
        g.add_edge(final, END)
    elif topo == "overparallel":
        non_final = sorted(n for n in specs if n != final)
        for nid in non_final:
            g.add_edge(START, nid)
        if non_final:
            g.add_edge(non_final, final)
        else:
            g.add_edge(START, final)
        g.add_edge(final, END)
    else:
        sys.exit(f"unknown topology {topo}")
    return g.compile()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("graph", type=Path)
    ap.add_argument("--agent", choices=list(MODELS), required=True)
    ap.add_argument("--mock", action="store_true")
    args = ap.parse_args()

    graph_spec = json.loads(args.graph.read_text(encoding="utf-8"))
    task = args.graph.stem.split(".")[0]
    task_dir = ROOT / "tasks" / task
    task_context = (task_dir / "task_context.md").read_text(encoding="utf-8")
    repo = task_dir / "repo"

    run_name = f"{args.graph.stem}--agent-{args.agent}" + ("--mock" if args.mock else "")
    run_dir = ROOT / "runs" / run_name
    run_dir.mkdir(parents=True, exist_ok=True)

    # seed workspace with every file any node reads or writes
    seed = {}
    for n in graph_spec["nodes"]:
        for p in set(n["reads"]) | set(n["writes"]):
            f = repo / p
            if f.exists() and p not in seed:
                seed[p] = {"writer": "__seed__",
                           "content": f.read_text(encoding="utf-8")}
    OVERWRITE_EVENTS.clear()
    app = build_graph(graph_spec, task_context, args.agent, args.mock, run_dir)
    t0 = time.time()
    final_state = app.invoke(
        {"files": seed, "node_outputs": {}, "trace": []},
        config={"recursion_limit": 100})
    wall = round(time.time() - t0, 2)

    final_out = final_state["node_outputs"].get(graph_spec["final_node"], {})
    (run_dir / "patch.diff").write_text(final_out.get("text", ""), encoding="utf-8")
    after = run_dir / "files_after"
    for p, entry in final_state["files"].items():
        if entry["writer"] != "__seed__":
            dest = after / p
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(entry["content"], encoding="utf-8")

    trace = {
        "graph": args.graph.name, "topology": graph_spec["topology"],
        "agent": args.agent, "mock": args.mock,
        "schedule": graph_spec["schedule"], "wall_s": wall,
        "total_cost_usd": round(sum(r["cost_usd"] for r in final_state["trace"]), 4),
        "overwrite_events": OVERWRITE_EVENTS,
        "nodes": final_state["trace"],
    }
    (run_dir / "trace.json").write_text(json.dumps(trace, indent=2), encoding="utf-8")
    failures = [r["node"] for r in final_state["trace"] if r["status"] != "success"]
    print(f"{run_name}: wall {wall}s, cost ${trace['total_cost_usd']}, "
          f"{'failures: ' + ','.join(failures) if failures else 'all nodes ok'}")


if __name__ == "__main__":
    main()
