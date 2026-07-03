# Findings — exploration pass

## Goal

Decide how (if at all) an execution **plan** can be obtained from MAD traces, so
that a later pass can build graph/statistics tooling on a sound footing.

## Corpus numbers (regenerable)

Any whole-corpus figure quoted in this document — totals, per-system /
per-benchmark / per-LLM failure rates, MAST mode and category frequencies,
benchmark↔system confounds, and human-label reliability — is produced by
`scripts/02_corpus_profile.py` and written to
[`corpus_profile.md`](corpus_profile.md). It is deterministic (no timestamps);
regenerate with:

```
python scripts/02_corpus_profile.py
```

Cite `corpus_profile.md` rather than pasting numbers here, so the source stays
the single point of truth.

## The two file shapes

- **`MAD_full_dataset.json`** (1242 records): `trace` is a dict
  `{"key", "index", "trajectory"}`; the log lives at `trace["trajectory"]`.
  Labels are in `mast_annotation`, a dict of the 14 MAST keys `1.1`..`3.3` with
  0/1 values.
- **`MAD_human_labelled_dataset.json`** (19 records): `trace` is the raw log
  **string**; labels are in `annotations`, a list of
  `{"failure mode", "annotator_1", "annotator_2", "annotator_3"}` rows.

The loader collapses both into one `TraceRecord`.

### 14 modes vs 18 human rows

The human file enumerates **18** "failure mode" rows but the taxonomy stored in
the full file has **14** modes. We reconcile by parsing the leading `X.Y` token
of each human row and mapping onto the 14 modes; the per-mode flag is the
**majority vote** of the three annotators (≥2 of 3). Rows with no `X.Y` token
(e.g. free-text "Other" notes) or a token outside the 14 modes are **logged and
skipped** — `loader._normalize_human` emits a `WARNING` for each. Raw annotator
booleans are retained on `TraceRecord.annotator_votes` for every row.

## Plan format: case (b) — reconstructable, not explicit

There is **no explicit plan artifact** serialized in the records. However, for
**ChatDev** traces the plan is **reconstructable from the log** because ChatDev
runs a fixed, phase-structured role-play:

1. **Phase markers** — `**[<Phase>]**`, regex `\*\*\[(.+?)\]\*\*`, give the
   ordered sequence of phases (e.g. *Start Chat → Coding → Code Review →
   Testing*). The ordered distinct list is the backbone of the plan.
2. **Role identifiers** — `Chief … Officer`, `Programmer`, `Code Reviewer`,
   `Software Test Engineer`, `Counselor` — identify the agents involved.
3. **Role-pair direction** — each exchange names a `user_role_name` and an
   `assistant_role_name`; the ordered pairs give the directed hand-offs between
   agents within/across phases.

Together, (phase sequence) × (role-pair directions) reconstruct the intended
plan/workflow without any separate plan field. This is what the README "Status"
line means by **case (b)**.

## What `inspect.py` extracts (this pass)

For a ChatDev trajectory:
- ordered distinct phase markers,
- a `Counter` of role identifiers,
- a `Counter` of `(user_role, assistant_role)` direction pairs.

## Plan-graph extractor (now built: `graph.py` + `stats.py`)

`src/mast_analysis/graph.py` now turns a ChatDev trajectory into a runnable
plan-graph and `src/mast_analysis/stats.py` computes per-graph metrics. It is
**extraction + analysis only** — no executor, no LangGraph, no LLM (running a
plan under alternative topologies is the next, separately-gated step).

**Graph model** (`networkx.DiGraph`, a DAG — all edges go forward in sequence):
- nodes: one `exchange` per agent turn (attrs `idx`, `user_role`,
  `assistant_role`), one `write` per `**[Update Codes]**`, one `run` per
  `**[Execute Detail]**`;
- edges: a `sequence` spine over consecutive nodes, plus `state` edges from each
  `write` to the next `run` and to every `exchange` until the next `write`;
- a separate role-interaction graph: `user_role -> assistant_role`, weighted by
  how often that direction occurs.

Parsing keys off the verified real-data line shapes
`**assistant_role_name** | <role> |` / `**user_role_name** | <role> |` and the
`**[...]**` process markers.

**`extract_record`** outputs `{graph_nodelink, role_nodelink (both
`node_link_data`, the runnable serialization), metrics, mast_flags, mas_name,
benchmark_name, trace_id}`. `iter_chatdev(loader)` streams it over every ChatDev
trace; `exemplars(loader, category="2.")` yields category-flagged traces with a
~1500-char excerpt around the first `Execute Detail` block.

**Metrics** per trace: `node_count, exchange_count, write_count, run_count,
depth` (`dag_longest_path_length`), `max_fan_out` (max out-degree of the role
graph), and `parallelizable_width` (maximum antichain via Dilworth — minimum
path cover = `node_count - max bipartite matching of the transitive closure`; no
antichain enumeration).

**Key result:** because the spine links every consecutive node, the dependency
DAG is a single chain, so `parallelizable_width` collapses to **1** for every
ChatDev plan — i.e. the modeled plan is strictly sequential. `depth` is
therefore `node_count - 1`. Regenerate the whole-corpus figures with
`python scripts/03_extract_chatdev.py` (ChatDev/ProgramDev), which prints the
per-trace table and mean/median and reports the observed width.

## Execution-topology rig (now built: `exec_lab.py`)

`src/mast_analysis/exec_lab.py` is the Task 2 experimental apparatus: a
**deterministic** rig (pure Python + networkx — no LLM, no API, no network, no
real threads) that validates failure-detection before any real agents exist.

**Plan model.** A plan is a `networkx.DiGraph` whose nodes carry `Task`
objects (`id`, `parents`, pure `step(state)`). `make_fanout_plan(width)` builds
`source -> width independent workers -> sink`; each worker contributes +1 and the
sink reads the accumulator, so the reference result is `width` and
`parallelizable_width == width` (verified with the **same** Dilworth routine
`compute_metrics` uses — see below).

**Grid.** `run_experiment(plan)` runs `{sequential, parallel, over_parallel}` ×
`{disciplined, ffa}`. Concurrency is modelled as an explicit two-phase schedule
(all reads from the round's start-state, then all writes), so:
- `disciplined` (each worker writes its own key; sink reduces) is always correct
  when deps are respected;
- `ffa` (unsynchronised read-modify-write on one key) **deterministically loses
  updates** under a concurrent topology (`parallel + ffa` -> value 1, not width);
- `over_parallel` fires every task in one round, so the sink reads **before** the
  workers write -> a **stale read** (incorrect for both disciplines).

Per cell it returns `correct, value, lost_updates, stale_read, cost` (cost =
rounds: sequential = n tasks, parallel = critical-path depth, over_parallel = 1).
The two coordination failures are reliably distinguishable: the write-race shows
`lost_updates>0` with `stale_read=False`, while `over_parallel` shows
`stale_read=True` regardless of discipline. Reproduce with
`python scripts/04_topology_grid.py`.

**Width is meaningful here.** On the *constructed* fan-out plan the workers are
genuinely independent, so `parallelizable_width` reports real exploitable
parallelism (`== width`). This contrasts with the *extracted* ChatDev logs,
where the sequence spine forces a total order and the same metric collapses to 1
— the metric is honest in both cases; the plans differ.

### Still out of scope (separately gated)

- Plugging **real agents** into the `Task` callbacks and choosing the real
  workload, plus any LLM/API call or LangGraph executor.
