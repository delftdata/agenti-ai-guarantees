# mast-plan-analysis

Exploration tooling for the **MAD** multi-agent failure dataset
([`mcemri/MAD`](https://huggingface.co/datasets/mcemri/MAD) on the Hugging Face
Hub), annotated with the 14-mode **MAST** failure taxonomy.

This is an *exploration* pass: load and normalize the two MAD files into one
record shape, and inspect ChatDev trajectory structure (phases + roles). Graph
extraction and statistics are intentionally **not** built yet — they are gated
on review of this pass.

## Layout

```
README.md
requirements.txt          # pinned
data/raw/                 # gitignored — never committed; the loader re-fetches
src/mast_analysis/
    loader.py             # download + normalize both MAD files -> TraceRecord
    inspect.py            # ChatDev phase / role / role-pair extraction
    graph.py              # ChatDev trajectory -> plan-graph (networkx DiGraph)
    stats.py              # per-graph structural metrics
    exec_lab.py           # deterministic execution-topology rig (Task 2)
scripts/01_explore.py     # filter to ChatDev/ProgramDev, inspect first 5
scripts/02_corpus_profile.py  # whole-corpus profile -> docs/corpus_profile.md
scripts/03_extract_chatdev.py # plan-graph metrics per ChatDev/ProgramDev trace
scripts/04_topology_grid.py   # run the topology x discipline grid (offline)
scripts/05_failed_vs_clean.py # failed vs clean structural split -> docs/failed_vs_clean.md
tests/
    fixtures/synthetic_mad.json
    test_loader.py        # runs fully offline against the fixture
docs/findings.md
```

## The two MAD files

| File | Shape | Records |
| --- | --- | --- |
| `MAD_full_dataset.json` | array; `trace = {"key","index","trajectory"}`, `mast_annotation` = 14 keys `1.1`..`3.3` (0/1) | 1242 |
| `MAD_human_labelled_dataset.json` | array; `trace` is a raw log string, `annotations` = list of `{"failure mode", annotator_1..3}` | 19 |

The loader normalizes both into a single `TraceRecord`. For the human file, the
18 "failure mode" rows are mapped onto the 14 MAST modes by parsing the leading
`X.Y` token, and a 0/1 flag per mode is derived by **majority vote** of the
three annotators (raw booleans are kept too). Rows that don't map are logged.

## Setup (Windows / PowerShell)

```powershell
cd mast-plan-analysis
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Python 3.11+ (developed on 3.14). On macOS/Linux use `python3 -m venv .venv` and `source .venv/bin/activate`.

## Run the exploration script

Downloads the raw files into `data/raw/` on first run (no API key needed), then
filters to `mas_name == "ChatDev"` / `benchmark_name == "ProgramDev"` and
inspects the first 5 traces:

```powershell
python scripts/01_explore.py
```

## Regenerate the corpus profile

Computes a reproducible whole-corpus profile (overview, MAST mode/category
frequencies, per-system / per-benchmark / per-LLM breakdowns, a benchmark↔system
confound check, and human-label reliability) and writes it to
`docs/corpus_profile.md`. Output is deterministic (no timestamps); the only
network access is the cached download inside the loader:

```powershell
python scripts/02_corpus_profile.py
```

## Extract ChatDev plan-graphs

Turns each ChatDev/ProgramDev trajectory into a plan-graph (`networkx.DiGraph`)
and prints per-trace structural metrics (`node_count`, `depth`, `max_fan_out`,
`parallelizable_width`, failures) plus mean/median. Extraction + analysis only —
nothing is executed and no LLM is called:

```powershell
python scripts/03_extract_chatdev.py
```

The spine links consecutive nodes, so the dependency DAG is one chain and
`parallelizable_width` collapses to 1 — confirming ChatDev plans are
near-sequential. See `docs/findings.md`.

## Run the execution-topology grid (Task 2 rig)

A deterministic apparatus (no LLM, API, network, or real threads) that runs a
fan-out plan under every `{topology} x {discipline}` cell and reliably detects
two coordination failures — a write-race (`ffa`) and a stale-read
(`over_parallel`) — as distinct modes:

```powershell
python scripts/04_topology_grid.py
```

Here `parallelizable_width` is meaningful (the constructed workers are genuinely
independent), unlike on the extracted ChatDev logs. See `docs/findings.md`.

## Run the tests

The tests run entirely offline against `tests/fixtures/synthetic_mad.json` — no
download or network access required:

```powershell
pytest
```

## Status

Plan format = **case (b)**: there is no explicit plan artifact in the data; the
plan is **reconstructable from ChatDev logs** via the **phase markers**
(`**[...]**`) plus the **role-pair direction** structure
(`user_role_name` → `assistant_role_name`). See `docs/findings.md`.
